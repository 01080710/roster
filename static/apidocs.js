// API 文件頁：載入 Swagger UI，規格由 /apidocs/openapi.json 依目前的 route 自動產生
(() => {
  const el = document.getElementById('swagger');
  SwaggerUIBundle({
    url: el.dataset.specUrl,
    dom_id: '#swagger',
    deepLinking: true,              // 網址帶 #，可以直接分享某一支 API
    docExpansion: 'list',           // 預設展開分組、收合每支 API
    defaultModelsExpandDepth: -1,   // 不顯示最下面的 Schemas 區塊
    // 用登入 cookie 送出的 POST 要帶 CSRF token（見 routes/common.py 的 check_csrf）
    requestInterceptor: req => { req.headers['X-CSRF-Token'] = el.dataset.csrf; return req; },
  });
})();
