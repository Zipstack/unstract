import "@testing-library/jest-dom";

// Layout is measured, so nothing may still be moving when we measure it.
// antd animates list items, tooltips and buttons on mount.
const style = document.createElement("style");
style.textContent = `*, *::before, *::after {
  animation-duration: 0s !important;
  animation-delay: 0s !important;
  transition-duration: 0s !important;
  transition-delay: 0s !important;
}`;
document.head.appendChild(style);
