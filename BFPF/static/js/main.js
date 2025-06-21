// static/js/main.js (개선 디버깅 + 썸네일 + 자동 업로드)

const roles = Array.from(document.querySelectorAll('.role'));
let uploaded = {};

roles.forEach(div => {
  const role = div.dataset.role;
  const input = div.querySelector('input');
  const canvas = div.querySelector('canvas');
  const btn = div.querySelector('.btn-upload'); // 유지하되 자동 업로드
  let ctx = canvas.getContext('2d');

  input.addEventListener('change', e => {
    const file = e.target.files[0];
    if (!file) return;
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      canvas.width = 224; canvas.height = 224;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, 224, 224);
      canvas.style.display = 'block';
      btn.disabled = false;
      // 자동 업로드 바로 실행
      uploadImage(role, canvas, btn);
    };
    img.onerror = () => {
      alert(`이미지를 불러올 수 없습니다: ${file.name}`);
    };
    img.src = url;
  });
});

async function uploadImage(role, canvas, btn){
  try {
    const blob = await new Promise(res => canvas.toBlob(res, 'image/jpeg'));
    const form = new FormData();
    form.append('role', role);
    form.append('image', blob, role + '.jpg');

    const res = await fetch('/upload', {
      method:'POST',
      body: form
    });
    const data = await res.json();

    if(data.status==='ok'){
      uploaded[role] = true;
      btn.disabled = true;
      checkReady();
      console.log(`[업로드 완료] ${role}`);
    } else {
      alert(`업로드 실패 (${role}): ${data.error || '서버 오류'}`);
    }
  } catch(err){
    console.error(`[업로드 중 오류] ${role}`, err);
    alert(`업로드 중 오류가 발생했습니다 (${role})`);
  }
}

document.getElementById('btn-compare').addEventListener('click', () => {
  fetch('/compare', { method:'POST' })
    .then(r => r.json())
    .then(data => showResults(data))
    .catch(err => {
      console.error('분석 요청 실패', err);
      alert('분석 요청 중 오류가 발생했습니다');
    });
});

function checkReady(){
  if(uploaded['child']) {
    document.getElementById('btn-compare').disabled = false;
  }
}

function showResults(data){
  const resDiv = document.getElementById('results');
  resDiv.innerHTML = '';
  if(data.best_match){
    resDiv.innerHTML += `<h2>가장 닮은 가족: ${data.best_match.label} (${data.best_match.similarity}%)</h2>`;
    data.all.forEach(r =>{
      resDiv.innerHTML += `<p>${r.label}: ${r.similarity}%</p>`;
    });
  } else {
    resDiv.innerHTML = `<p>분석할 사진이 충분하지 않습니다.</p>`;
  }
}

