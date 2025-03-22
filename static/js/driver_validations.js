document.addEventListener("DOMContentLoaded", function () {
    const form = document.getElementById("driverForm");
  
    // Función para mostrar mensajes dinámicos en la parte superior
    function showMessage(message, type = "error") {
      let messageBox = document.getElementById("floatingMessage");
      if (!messageBox) {
        messageBox = document.createElement("div");
        messageBox.id = "floatingMessage";
        document.body.appendChild(messageBox);
      }
  
      messageBox.innerText = message;
      messageBox.style.backgroundColor = type === "error" ? "red" : "green";
      messageBox.style.color = "white";
      messageBox.style.padding = "15px";
      messageBox.style.borderRadius = "8px";
      messageBox.style.position = "fixed";
      messageBox.style.top = "20%"; // Ahora está más arriba
      messageBox.style.left = "50%";
      messageBox.style.transform = "translate(-50%, -50%)";
      messageBox.style.fontSize = "16px";
      messageBox.style.textAlign = "center";
      messageBox.style.zIndex = "9999";
      messageBox.style.boxShadow = "0 0 10px rgba(0,0,0,0.3)";
      
      setTimeout(() => {
        messageBox.remove();
      }, 3000);
    }
  
    form.addEventListener("submit", function (event) {
      let hasError = false;
      const nombre = document.getElementById("nombre").value.trim();
      const telefono = document.getElementById("telefono").value.trim();
      const CI = document.getElementById("CI").value.trim();
      const fechaNacimiento = document.getElementById("fecha_nacimiento").value;
      const fechaEmision = document.getElementById("fecha_emision_licencia").value;
      const fechaExpiracion = document.getElementById("fecha_expiracion_licencia").value;
  
      const today = new Date();
      today.setHours(0, 0, 0, 0); // Eliminamos la hora para evitar errores
  
      // Validar que el nombre solo contenga letras y espacios
      if (!nombre.match(/^[A-Za-z\s]+$/)) {
        showMessage("El nombre solo puede contener letras y espacios.", "error");
        hasError = true;
      }
  
      // Validar que el teléfono solo contenga números
      if (!telefono.match(/^\d+$/)) {
        showMessage("El teléfono solo puede contener números.", "error");
        hasError = true;
      }
  
      // Validar que el CI solo contenga números
      if (!CI.match(/^\d+$/)) {
        showMessage("El CI solo puede contener números.", "error");
        hasError = true;
      }
  
      // Validar que la fecha de nacimiento esté ingresada y refleje al menos 21 años
      if (!fechaNacimiento) {
        showMessage("Debe ingresar la fecha de nacimiento.", "error");
        hasError = true;
      } else {
        const birthDate = new Date(fechaNacimiento);
        const minBirthDate = new Date(today);
        minBirthDate.setFullYear(minBirthDate.getFullYear() - 21); // 21 años atrás
  
        if (birthDate > minBirthDate) {
          showMessage("El conductor debe tener al menos 21 años.", "error");
          hasError = true;
        }
      }
  
      // Validar que la fecha de emisión esté ingresada y sea anterior o igual a hoy
      if (!fechaEmision) {
        showMessage("Debe ingresar la fecha de emisión de la licencia.", "error");
        hasError = true;
      } else {
        const emisionDate = new Date(fechaEmision);
        if (emisionDate > today) {
          showMessage("La fecha de emisión no puede ser posterior a hoy.", "error");
          hasError = true;
        }
      }
  
      // Validar que la fecha de expiración esté ingresada y sea posterior a hoy
      if (!fechaExpiracion) {
        showMessage("Debe ingresar la fecha de expiración de la licencia.", "error");
        hasError = true;
      } else {
        const expiracionDate = new Date(fechaExpiracion);
        if (expiracionDate <= today) {
          showMessage("La fecha de expiración debe ser posterior a hoy.", "error");
          hasError = true;
        }
      }
  
      // Validar que la fecha de emisión sea anterior a la de expiración
      if (fechaEmision && fechaExpiracion) {
        const emisionDate = new Date(fechaEmision);
        const expiracionDate = new Date(fechaExpiracion);
        if (emisionDate >= expiracionDate) {
          showMessage("La fecha de emisión debe ser anterior a la fecha de expiración.", "error");
          hasError = true;
        }
      }
  
      // Si hay errores, evitamos que el formulario se envíe y ocultamos la animación de carga
      if (hasError) {
        event.preventDefault();
        document.getElementById("loadingOverlay").style.display = "none";
      } else {
        showMessage("Registro exitoso!", "success");
      }
    });
  });
  