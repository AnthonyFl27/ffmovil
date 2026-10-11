// Animaciones al desplazar de las páginas públicas (RF-58, RNF-20; plan sec. 6.3).
// Se carga en <head> sin defer: la clase `js` llega antes de pintar. Sin JavaScript
// la clase nunca se añade y el CSS no oculta nada.
document.documentElement.classList.add("js");

document.addEventListener("DOMContentLoaded", function () {
  var elementos = document.querySelectorAll(".revelar");
  function mostrar(elemento) {
    elemento.classList.add("visible");
  }
  if (!("IntersectionObserver" in window)) {
    elementos.forEach(mostrar);
    return;
  }
  var observador = new IntersectionObserver(
    function (entradas) {
      entradas.forEach(function (entrada) {
        if (entrada.isIntersecting) {
          mostrar(entrada.target);
          observador.unobserve(entrada.target);
        }
      });
    },
    { threshold: 0.15 }
  );
  elementos.forEach(function (elemento) {
    observador.observe(elemento);
  });
});
