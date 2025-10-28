document.addEventListener("DOMContentLoaded", () => {
  const canvas = document.getElementById('network-canvas');
  const ctx = canvas.getContext('2d');

  let width = canvas.width = window.innerWidth;
  let height = canvas.height = window.innerHeight;

  const nodesCount = 50; // количество точек
  const nodes = [];

  // Создаем точки
  for (let i = 0; i < nodesCount; i++) {
    nodes.push({
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.5, // скорость X
      vy: (Math.random() - 0.5) * 0.5, // скорость Y
      radius: 2 + Math.random() * 2
    });
  }

  // Рисуем точки и линии
  function draw() {
    ctx.clearRect(0, 0, width, height);

    // Рисуем линии между близкими точками
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const dx = nodes[i].x - nodes[j].x;
        const dy = nodes[i].y - nodes[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 120) { // соединяем если близко
          ctx.strokeStyle = `rgba(14,165,233,${1 - dist / 120})`;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(nodes[i].x, nodes[i].y);
          ctx.lineTo(nodes[j].x, nodes[j].y);
          ctx.stroke();
        }
      }
    }

    // Рисуем точки
    nodes.forEach(n => {
      ctx.fillStyle = '#0ea5e9';
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.radius, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  // Анимация движения
  function update() {
    nodes.forEach(n => {
      n.x += n.vx;
      n.y += n.vy;

      // отскок от стенок
      if (n.x < 0 || n.x > width) n.vx *= -1;
      if (n.y < 0 || n.y > height) n.vy *= -1;
    });
    draw();
    requestAnimationFrame(update);
  }

  update();

  // Обновление при ресайзе
  window.addEventListener('resize', () => {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  });
})