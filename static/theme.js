// 主題：預設亮色；使用者選過深色時記在瀏覽器（localStorage），在畫面繪出前套用，避免閃爍
try { if (localStorage.getItem('roster-theme') === 'dark') document.documentElement.dataset.theme = 'dark'; } catch (e) {}
