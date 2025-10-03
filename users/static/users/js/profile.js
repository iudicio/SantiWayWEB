document.addEventListener("DOMContentLoaded", ()=>{
    const statuses = {order: "order", create: "create", ready: "ready"};

    const androidBtn =  document.querySelectorAll(".apk-btn");

   androidBtn.forEach(element => {
        element.addEventListener("click", ()=>{
            let status = element.getAttribute("data-status");
            let row = element.closest("tr");
            if (status == statuses.order) {
                element.textContent = "На сборке";
                element.setAttribute("data-status", statuses.create);
                row.setAttribute("data-status", statuses.create);
                // Отправить запрос на сервер
            } else if (status == statuses.create){
                // Отправить запрос на сервер
                const response = 1;
                if (response) {
                    element.textContent = "Скачать APK";
                    element.setAttribute("data-status", statuses.ready);
                    row.setAttribute("data-status", statuses.ready);
                }
            }
        })
    })

   document.querySelectorAll(".mono").forEach(el => {
        el.addEventListener("click", () => {
            const original = el.textContent;
            el.textContent = 'Скопировано!';
            const key = el.textContent.trim();
            navigator.clipboard.writeText(original).then(() => {
              el.classList.add("copied");
              setTimeout(() => el.classList.remove("copied"), 1500);
              setTimeout(() => el.textContent = original, 1500);
            });
       });
   });

})