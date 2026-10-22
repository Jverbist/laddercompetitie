(() => {
  const anime = window.anime;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  if (!anime || reducedMotion) return;

  const { animate, stagger } = anime;

  animate(".ambient-orb-orange", {
    x: [0, 75, -35, 0],
    y: [0, 35, 90, 0],
    scale: [1, 1.18, 0.92, 1],
    duration: 24000,
    ease: "inOutSine",
    loop: true,
  });

  animate(".ambient-orb-blue", {
    x: [0, -90, 25, 0],
    y: [0, 75, -35, 0],
    scale: [1, 0.9, 1.16, 1],
    duration: 29000,
    ease: "inOutSine",
    loop: true,
    delay: 700,
  });

  animate(".ambient-orb-violet", {
    x: [0, 55, -75, 0],
    y: [0, -60, 20, 0],
    scale: [1, 1.12, 0.94, 1],
    duration: 26000,
    ease: "inOutSine",
    loop: true,
    delay: 1300,
  });

  animate(".page .card", {
    opacity: [0, 1],
    y: [14, 0],
    duration: 520,
    delay: stagger(65),
    ease: "outCubic",
    onBegin: () => document.body.classList.add("motion-ready"),
  });

  document.querySelectorAll("[data-bar]").forEach((bar, index) => {
    animate(bar, {
      width: ["0%", `${bar.dataset.bar}%`],
      duration: 900,
      delay: 250 + index * 80,
      ease: "outExpo",
    });
  });

  document.querySelectorAll("[data-count]").forEach((el) => {
    const target = Number(el.dataset.count);
    const counter = { value: 0 };
    animate(counter, {
      value: target,
      duration: 1100,
      ease: "outExpo",
      onUpdate: () => { el.textContent = Math.round(counter.value); },
    });
  });

  animate(".podium-step", {
    y: [30, 0],
    opacity: [0, 1],
    duration: 700,
    delay: stagger(140),
    ease: "outBack",
  });

  document.querySelectorAll(".button").forEach((button) => {
    const lift = () => animate(button, {
      y: -3,
      scale: 1.025,
      duration: 180,
      ease: "outQuad",
    });
    const settle = () => animate(button, {
      y: 0,
      scale: 1,
      duration: 220,
      ease: "outElastic(1, .65)",
    });

    button.addEventListener("pointerenter", lift);
    button.addEventListener("pointerleave", settle);
    button.addEventListener("focus", lift);
    button.addEventListener("blur", settle);
  });
})();
