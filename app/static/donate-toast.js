(() => {
  const toast = document.getElementById("donate-toast");
  if (!toast || sessionStorage.getItem("donate-toast-seen")) return;
  // Only shows for roughly one in three visits, at a random moment.
  if (Math.random() > 0.34) return;
  setTimeout(() => {
    toast.hidden = false;
    requestAnimationFrame(() => toast.classList.add("show"));
    sessionStorage.setItem("donate-toast-seen", "1");
    setTimeout(() => toast.classList.remove("show"), 15000);
  }, 5000 + Math.random() * 25000);
  toast.querySelector(".toast-close").addEventListener("click", () => toast.classList.remove("show"));
})();
