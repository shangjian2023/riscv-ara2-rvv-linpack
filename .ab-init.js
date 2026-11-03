(function () {
  if (window.__hooked) return;
  window.__hooked = true;
  window.__captures = [];
  var origOpen = XMLHttpRequest.prototype.open;
  var origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url) {
    this.__url = url;
    try {
      var u = String(url);
      if (u.indexOf('/api/article/index') !== -1) {
        u = u.replace('pagesize=9', 'pagesize=200');
        this.__url = u;
        arguments[1] = u;
      }
      if (u.indexOf('/api/subject/index') !== -1) {
        // keep original
      }
    } catch (e) {}
    return origOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function () {
    var xhr = this;
    xhr.addEventListener('load', function () {
      try {
        if (xhr.__url && String(xhr.__url).indexOf('/api/') !== -1) {
          window.__captures.push({ url: xhr.__url, status: xhr.status, body: xhr.responseText });
        }
      } catch (e) {}
    });
    return origSend.apply(this, arguments);
  };
  var origFetch = window.fetch;
  if (origFetch) {
    window.fetch = function (input, init) {
      var url = typeof input === 'string' ? input : (input && input.url) || '';
      return origFetch.apply(this, arguments).then(function (resp) {
        try {
          if (url.indexOf('/api/') !== -1) {
            resp.clone().text().then(function (t) {
              window.__captures.push({ url: url, status: resp.status, body: t });
            });
          }
        } catch (e) {}
        return resp;
      });
    };
  }
})();
