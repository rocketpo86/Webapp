// static/js/main.js
const roles = Array.from(document.querySelectorAll('.role'));
let uploaded = {};

roles.forEach(div => {
  const role = div.dataset.role;
  const input = div.querySelector('input');
  const canvas = div.querySelector('canvas');
  const btn = div.querySelector('.btn-upload');
  let ctx = canvas.getContext('2d');

  input.addEventListener('change', e => {
    const file = e.target.files[0];
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      canvas.width = 224; canvas.height = 224;
      ctx.drawImage(img, 0, 0, 224, 224);
      canvas.style.display = 'block';
      btn.disabled = false;
    };
    img.src = url;
  });

  btn.addEventListener('click', async () => {
    const blob = await new Promise(res => canvas.toBlob(res, 'image/jpeg'));
    const form = new FormData();
    form.append('role', role);
    form.append('image', blob, role + '.jpg');
    fetch('/upload', { method:'POST', body: form })
      .then(r => r.json())
      .then(data => {
        if(data.status==='ok'){
          uploaded[role]=true;
          btn.disabled = true;
          checkReady();
        }
      });
  });
});

document.getElementById('btn-compare').addEventListener('click', () => {
  fetch('/compare',{method:'POST'})
    .then(r=>r.json())
    .then(data=> showResults(data));
});

function checkReady(){
  if(uploaded['child']) document.getElementById('btn-compare').disabled = false;
}

function showResults(data){
  const resDiv = document.getElementById('results');
  resDiv.innerHTML = '';
  if(data.best_match){
    resDiv.innerHTML += `<h2>가장 닮은 가족: ${data.best_match.label} (${data.best_match.similarity}%)</h2>`;
    data.all.forEach(r=>{
      resDiv.innerHTML += `<p>${r.label}: ${r.similarity}%</p>`;
    });
  }
}
