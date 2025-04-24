const recordBtn = document.getElementById("record");
const stopBtn   = document.getElementById("stop");
let recorder, chunks = [];

recordBtn.onclick = async () => {
  recordBtn.disabled = true;
  stopBtn.disabled   = false;
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  recorder = new MediaRecorder(stream);
  recorder.ondataavailable = e => chunks.push(e.data);
  recorder.start();
};

stopBtn.onclick = () => {
  stopBtn.disabled = true;
  recordBtn.disabled = false;
  recorder.stop();
  recorder.onstop = async () => {
    const blob = new Blob(chunks, { type: "audio/webm" });
    const form = new FormData();
    form.append("file", blob, "input.webm");
    const res = await fetch("http://localhost:8000/transcribe", {
      method: "POST",
      body: form
    });
    if (!res.ok) return alert("PDF generation failed");
    const pdfBlob = await res.blob();
    const url = URL.createObjectURL(pdfBlob);
    const a = document.createElement("a");
    a.href = url; a.download = "filled.pdf";
    document.body.append(a);
    a.click(); a.remove();
  };
};
