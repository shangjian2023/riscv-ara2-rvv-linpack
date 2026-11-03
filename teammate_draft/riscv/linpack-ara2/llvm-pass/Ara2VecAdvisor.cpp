// Ara2VecAdvisor.cpp - LLVM NewPM plugin pass (demo of the Ara2 cost model
// as a compiler pass).
//
// What it does (runs on riscv64 targets, pre-vectorization IR):
//   1. Walks loop nests via LoopInfo.
//   2. Finds "GEMM-ish" innermost loops: FP multiply/add chain over f64 with
//      >=1 load and >=1 store (the auto-vectorizable inner j loop of ijk
//      DGEMM). Measures its per-iteration vector-op mix:
//         fpu ops  = FMul + FAdd + FSub  (future vfmacc)
//         mem ops  = Load + Store        (future vle/vse, 3 in naive form)
//      Reuse = mem/fpu. The naive form has reuse 3 -> VLSU-bound at ~17% of
//      Ara2 peak (each FP64 vector FMA needs 8L B/cyc of streams but VLSU
//      offers 4L B/cyc).
//   3. Rule fix (Rule 1 - bandwidth matching): unroll the MIDDLE (k) loop by
//      MR = clamp(2*mem/fpu, 4, 8) so C load/store amortize over MR FMA chains;
//      B stays 1 stream per FMA. Predicted transfer/fma drops 3 -> 1+2/MR.
//      Injects llvm.loop.unroll.count and llvm.loop.unroll_and_jam.count
//      metadata on the middle loop, llvm.loop.vectorize.enable on the inner.
//   4. Prints an ARA2ADVISE line per decision (machine-parsable evidence).
//
// Usage (see scripts/llvm_pass_flow.sh):
//   clang-18 -O1 -emit-llvm -S src/dgemm_naive.c -o naive.ll
//   opt-18 -load-pass-plugin=libAra2Advisor.so -passes=function(ara2-advisor) \
//          -S naive.ll -o naive.adj.ll
//   clang-18 -O2 ... naive.adj.ll -c   # unroll passes honor the metadata
#include "llvm/ADT/StringRef.h"
#include "llvm/Analysis/LoopInfo.h"
#include "llvm/IR/Dominators.h"
#include "llvm/IR/Function.h"
#include "llvm/IR/IRBuilder.h"
#include "llvm/IR/Instructions.h"
#include "llvm/IR/Module.h"
#include "llvm/IR/PassManager.h"
#include "llvm/Passes/PassBuilder.h"
#include "llvm/Passes/PassPlugin.h"
#include <cstdio>

using namespace llvm;

namespace {

bool isF64(Type *T) { return T->isDoubleTy(); }

struct LoopMix {
  int fpu = 0;  // FMul/FAdd/FSub on f64
  int mem = 0;  // f64 loads + stores
};

LoopMix scanBody(const Loop &L) {
  LoopMix M;
  for (BasicBlock *BB : L.getBlocks()) {
    // exclude blocks of sub-loops so innermost body is counted
    if (L.getSubLoops().size() && BB == L.getHeader())
      continue;
    for (Instruction &I : *BB) {
      if (auto *Ld = dyn_cast<LoadInst>(&I)) {
        if (isF64(Ld->getType())) M.mem++;
      } else if (auto *St = dyn_cast<StoreInst>(&I)) {
        if (isF64(St->getValueOperand()->getType())) M.mem++;
      } else if (I.isBinaryOp()) {
        unsigned Op = I.getOpcode();
        if (Op == Instruction::FMul || Op == Instruction::FAdd ||
            Op == Instruction::FSub) {
          if (isF64(I.getType())) M.fpu++;
        }
      } else if (auto *CI = dyn_cast<CallInst>(&I)) {
        // -ffp-contract=on (clang default) folds a*b+c into llvm.fmuladd
        Function *Callee = CI->getCalledFunction();
        if (Callee && Callee->getName().starts_with("llvm.fmuladd.") &&
            isF64(CI->getType()))
          M.fpu++; // one fmuladd = one future vfmacc
      }
    }
  }
  return M;
}

/// Replace/add "llvm.loop.<key> = i32 <val>" options on the loop's loop ID.
/// The ID can live on the header terminator or on a latch; we rewrite every
/// terminator in the loop that carries one (and the header otherwise), so
/// readers see a consistent, updated ID. Conflicting markers of the same
/// family (e.g. llvm.loop.unroll.disable written by an earlier pass) are
/// dropped so the advisor's count wins.
void setLoopIntOption(Loop *L, const char *Key, uint32_t Val) {
  BasicBlock *H = L->getHeader();
  LLVMContext &Ctx = H->getContext();
  MDNode *Cur = L->getLoopID();
  StringRef KeyS(Key);
  StringRef Family = KeyS.substr(0, KeyS.rfind('.')); // llvm.loop.unroll[...]
  SmallVector<Metadata *, 8> MDs;
  if (Cur) {
    for (unsigned i = 1; i < Cur->getNumOperands(); ++i) {
      Metadata *Op = Cur->getOperand(i).get();
      bool drop = false;
      if (MDNode *N = dyn_cast<MDNode>(Op))
        if (N->getNumOperands())
          if (auto *S = dyn_cast<MDString>(N->getOperand(0).get())) {
            StringRef O = S->getString();
            drop = O == KeyS || O == (Family + ".disable").str() ||
                   O == (Family + ".enable").str();
          }
      if (!drop)
        MDs.push_back(Op);
    }
  }
  Metadata *Opts[2] = {MDString::get(Ctx, KeyS),
                       ConstantAsMetadata::get(ConstantInt::get(
                           Type::getInt32Ty(Ctx), Val, false))};
  MDs.push_back(MDNode::get(Ctx, Opts));
  // Loop IDs must be self-referential (operand 0 == the node itself):
  // Loop::getLoopID() and every consumer pass ignore them otherwise.
  MDs.insert(MDs.begin(), nullptr);
  MDNode *NewID = MDNode::getDistinct(Ctx, MDs);
  NewID->replaceOperandWith(0, NewID);
  // apply everywhere an ID is attached (header + latches)
  H->getTerminator()->setMetadata("llvm.loop", NewID);
  SmallVector<BasicBlock *, 4> Latches;
  L->getLoopLatches(Latches);
  for (BasicBlock *B : Latches)
    if (B != H)
      B->getTerminator()->setMetadata("llvm.loop", NewID);
}

struct Ara2VecAdvisor : PassInfoMixin<Ara2VecAdvisor> {
  PreservedAnalyses run(Function &F, FunctionAnalysisManager &AM) {
    Module *M = F.getParent();
    if (!M)
      return PreservedAnalyses::all();
    bool IsRV = M->getTargetTriple().starts_with("riscv64");
    auto &LI = AM.getResult<LoopAnalysis>(F);
    bool Changed = false;
    for (Loop *Top : LI) {
      for (Loop *L : Top->getLoopsInPreorder()) {
        if (!L->isInnermost())
          continue;
        LoopMix Mx = scanBody(*L);
        errs() << "ARA2SCAN function=" << F.getName() << " rv=" << IsRV
               << " fpu=" << Mx.fpu << " mem=" << Mx.mem << "\n";
        if (!IsRV)
          continue;
        if (Mx.fpu == 0 || Mx.mem == 0)
          continue;
        double reuse = (double)Mx.mem / (double)Mx.fpu;
        if (reuse < 1.5) // already register-blocked shape; leave alone
          continue;
        int mr = (int)(2.0 * reuse + 0.5);
        if (mr < 4) mr = 4;
        if (mr > 8) mr = 8;
        Loop *Mid = L->getParentLoop();
        if (!Mid)
          continue;
        DebugLoc Loc = L->getStartLoc();
        std::string LocStr = "unknown";
        if (Loc) {
          LocStr = (Twine(Loc->getFilename()) + ":" + Twine(Loc->getLine())).str();
        }
        // Rule 1 (bandwidth matching): MR chosen so that transfers per FMA
        // fall to 1 + 2/MR, i.e. VLSU cycles <= FPU cycles on Ara2 (4L vs 8L).
        setLoopIntOption(Mid, "llvm.loop.unroll.count", (uint32_t)mr);
        setLoopIntOption(Mid, "llvm.loop.unroll_and_jam.count", (uint32_t)mr);
        setLoopIntOption(L, "llvm.loop.unroll.count", 1); // keep inner tight
        Changed = true;
        errs() << "ARA2ADVISE function=" << F.getName()
               << " inner=" << LocStr << " fpu=" << Mx.fpu << " mem=" << Mx.mem
               << " reuse=" << reuse << " -> unroll_k(MR)=" << mr
               << " (Rule1: bandwidth matching)\n";
      }
    }
    return Changed ? PreservedAnalyses::none() : PreservedAnalyses::all();
  }
};

} // namespace

extern "C" LLVM_ATTRIBUTE_WEAK PassPluginLibraryInfo llvmGetPassPluginInfo() {
  return {LLVM_PLUGIN_API_VERSION, "Ara2VecAdvisor", LLVM_VERSION_STRING,
          [](PassBuilder &PB) {
            PB.registerPipelineParsingCallback(
                [](StringRef Name, FunctionPassManager &FPM,
                   ArrayRef<PassBuilder::PipelineElement>) {
                  if (Name == "ara2-advisor") {
                    FPM.addPass(Ara2VecAdvisor());
                    return true;
                  }
                  return false;
                });
          }};
}
