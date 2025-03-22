// ver_pasajes.js

function openPassengerModal(seatName) {
  var details = passengerMap[seatName];
  var detailsDiv = document.getElementById("passengerDetails");

  if (details) {
    detailsDiv.innerHTML = `
      <p><strong>Asiento:</strong> ${details.seatName}</p>
      <p><strong>Nombre:</strong> ${details.nombre || details.passengerName || "No registrado"}</p>
      <p><strong>C.I/Pasaporte:</strong> ${details.ci || "N/A"}</p>
      <p><strong>Edad:</strong> ${details.edad || "N/A"}</p>
      <p><strong>Teléfono:</strong> ${details.phone || "N/A"}</p>
      <p><strong>País:</strong> ${details.pais || "N/A"}</p>
      <p><strong>Precio:</strong> ${details.price ? details.price + " Bs" : "N/A"}</p>
      <hr>
      <p><strong>Vendido por:</strong> ${details.vendido_por || "N/A"}</p>
      <p><strong>Origen de venta:</strong> ${details.origen_venta || "N/A"}</p>
    `;
  } else {
    detailsDiv.innerHTML = "<p>No se encontraron detalles para este asiento.</p>";
  }
  document.getElementById("passengerModal").style.display = "block";
}

function closePassengerModal() {
  document.getElementById("passengerModal").style.display = "none";
}

// Cerrar modal al hacer clic fuera
window.addEventListener("click", function(event) {
  var modal = document.getElementById("passengerModal");
  if (event.target === modal) {
    closePassengerModal();
  }
});
