
function fillList(id, elements){
  const list = document.getElementById(id);

  for (let key in elements) {
    let label = document.createElement("label");
    label.classList = "custom-checkbox";

    let checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = key;
    label.appendChild(checkbox);
    label.appendChild(document.createTextNode(elements[key]));
    list.appendChild(label)
  }
}

// Возвращает apiKey и его имя
async function getApiKeys(){
    const apiKeysResponse = await fetch("/api/api-key/", {
      method: "GET",
    });
    const apiKeys = await apiKeysResponse.json();
    console.log("API Keys:", apiKeys);
    return apiKeys
}

async function getDevices(apiKeys){
  const devicesResponse = await fetch("/api/userinfo/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      'X-CSRFToken': getCookie('csrftoken')
    },
    body: JSON.stringify({
      api_keys: apiKeys
    })
  });

  const devices = await devicesResponse.json();
  console.log("Devices:", devices);
}

function getFolders(devices){

}

function getCookie(name){
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}