(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const transcript = $("transcript"), notes = $("notes"), title = $("lectureTitle");
  const mic = $("recordMic"), screen = $("recordScreen"), stop = $("stopRecord");
  const fileInput = $("lectureFile"), importButton = $("transcribeFile"), status = $("recordStatus");
  const message = $("lectureMessage"), timer = $("recordTimer"), recordBox = document.querySelector(".lecture-record-status");
  const draftKey = "constant-lecture-draft-v1";
  let draftOwner = null, identityRevision = 0, completedNotes = {}, transcriptionReceipts = {};
  window.LectureNotesOwner=()=>draftOwner;
  window.LectureCompletedState=()=>completedNotes;
  window.LectureSetCompletedState=value=>{completedNotes=value;return save();};
  window.LectureNewDocument=()=>{
    if(recording||starting||closing||window.LectureTranscriptionBusy?.())return false;
    completedNotes={};transcriptionReceipts={};title.value="";transcript.value="";notes.value="";countWords();save();return true;
  };
  window.LectureAppendTranscriptOnce=(recordingId,clipIndex,text)=>{
    if(draftOwner===null||!Number.isInteger(clipIndex)||clipIndex<0)return false;
    const previous=transcriptionReceipts[recordingId];
    if(Number.isInteger(previous)&&previous>=clipIndex)return true;
    const before=transcript.value;
    transcript.value=window.LectureTranscriptCore.appendVerbatim(before,text);
    transcriptionReceipts[recordingId]=clipIndex;
    if(save()!==true){
      transcript.value=before;
      if(previous===undefined)delete transcriptionReceipts[recordingId];else transcriptionReceipts[recordingId]=previous;
      return false;
    }
    transcript.dispatchEvent(new Event("input",{bubbles:true}));
    return true;
  };
  // Dźwięk nie przechodzi już przez płatne API.
  let session = null, streams = [], recording = false, starting = false, closing = false, began = 0;
  let captureGeneration = 0, mixing = null;
  window.LectureRecordingState=()=>({recording,starting,closing,ready:draftOwner!==null});
  let interval = null, objectUrl = null, previewRecordingId = null;
  const includeMic = $("includeMicrophone"), store = window.LectureRecordingStore;
  let autosaveTimer = null, mediaBlob = null;
  $("footerYear").textContent = new Date().getFullYear();

  function inform(text, kind = "") {
    message.className = "lecture-message" + (kind ? " " + kind : "");
    message.textContent = text;
  }
  function save() {
    if (draftOwner === null) return;
    try { localStorage.setItem(draftKey + ":" + draftOwner, JSON.stringify({title:title.value,transcript:transcript.value,notes:notes.value,completedNotes,transcriptionReceipts})); return true; }
    catch { inform("Brak miejsca na lokalny szkic. Pobierz notatki na urządzenie.", "error"); return false; }
  }
  function scheduleSave() { clearTimeout(autosaveTimer); autosaveTimer = setTimeout(save, 400); }
  window.LectureSaveDraftNow=save;
  function switchOwner(next) {
    next = next || "guest";
    if (next === draftOwner) return;
    if (draftOwner !== null) {
      captureGeneration++;
      if (recording || starting) void finishRecording();
      mediaBlob = null;
      fileInput.value = "";
      importButton.disabled = true;
      $("mediaPlayer").hidden = true;
      $("audioPreview").pause(); $("videoPreview").pause();
      if (objectUrl) { URL.revokeObjectURL(objectUrl); objectUrl = null; }
    }
    clearTimeout(autosaveTimer);
    if (draftOwner !== null) save();
    draftOwner = next;
    $("recordingsList").replaceChildren();
    $("recordingsEmpty").hidden=false;
    title.value = ""; transcript.value = ""; notes.value = ""; completedNotes={};transcriptionReceipts={};
    try {
      const draft = JSON.parse(localStorage.getItem(draftKey + ":" + draftOwner) || "null");
      if (draft && typeof draft === "object") {
        title.value = String(draft.title || "").slice(0,120);
        transcript.value = String(draft.transcript || "");
        notes.value = String(draft.notes || "");
        for(const kind of ["transcript","note"]){
          const meta=draft.completedNotes?.[kind];
          if(meta?.completed&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(meta.id||""))completedNotes[kind]={id:meta.id,completed:true};
        }
        for(const [id,index] of Object.entries(draft.transcriptionReceipts||{}))if(Number.isInteger(index)&&index>=0)transcriptionReceipts[id]=index;
      }
    } catch {}
    countWords();
    setRecordingControls();
    void renderRecordings();
    window.dispatchEvent(new CustomEvent("lecture-account-change",{detail:{owner:draftOwner}}));
  }
  if (window.AppSupabase?.auth) {
    const revision = ++identityRevision;
    AppSupabase.auth.getSession().then(({data}) => {
      if (revision === identityRevision) switchOwner(data?.session?.user?.id || "guest");
    }).catch(() => { if (revision === identityRevision) switchOwner("guest"); });
    AppSupabase.auth.onAuthStateChange((_event,session) => {
      ++identityRevision;
      switchOwner(session?.user?.id || "guest");
    });
  } else switchOwner("guest");
  [title,transcript,notes].forEach(element => element.addEventListener("input", () => {
    scheduleSave();
    if (element === transcript) countWords();
  }));
  function countWords() {
    $("wordCount").textContent = (transcript.value.trim().match(/\S+/g) || []).length + " słów";
  }
  countWords();
  function stamp() {
    const seconds = (Date.now() - began) / 1000;
    timer.textContent = window.LectureTranscriptCore.formatTime(Math.min(7200, Math.max(0, seconds))) + " / 02:00:00";
  }
  function download(content, filename, type) {
    const url = URL.createObjectURL(new Blob([content], {type}));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; document.body.appendChild(anchor); anchor.click(); anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  }
  function safeName() {
    return (title.value.trim() || "wyklad").normalize("NFD").replace(/[\u0300-\u036f]/g,"").replace(/[^\w\-]+/g,"-").slice(0,70) || "wyklad";
  }
  $("downloadTranscript").addEventListener("click", () => {
    if (!transcript.value.trim()) return inform("Brak transkrypcji do pobrania.", "error");
    download(transcript.value, safeName() + "-transkrypcja.txt", "text/plain;charset=utf-8");
  });
  $("downloadNotes").addEventListener("click", () => {
    if (!notes.value.trim()) return inform("Najpierw przygotuj notatkę.", "error");
    download(notes.value, safeName() + "-notatka.md", "text/markdown;charset=utf-8");
  });
  $("textFile").addEventListener("change", async event => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) return inform("Plik TXT ma ponad 2 MB. Wklej krótszy tekst.", "error");
    try { transcript.value = await file.text(); countWords(); save(); inform("Transkrypcja została wczytana.", "success"); }
    catch { inform("Nie udało się odczytać pliku TXT.", "error"); }
    event.target.value = "";
  });
  function releaseStreams() {
    for (const stream of streams) for (const track of stream.getTracks()) track.stop();
    streams = [];
    if (mixing) { void mixing.close().catch(()=>{}); mixing=null; }
  }
  function setRecordingControls() {
    mic.disabled=recording||starting||closing||draftOwner===null; screen.disabled=recording||starting||closing||draftOwner===null;
    includeMic.disabled=recording||starting||closing;
    fileInput.disabled=recording||starting||closing;
    document.querySelectorAll("[data-recording-remove]").forEach(button=>{button.disabled=recording||starting||closing;});
    stop.disabled=!recording&&!starting;
    stop.textContent=starting&&!recording?"Anuluj rozpoczęcie":"■ Zakończ nagrywanie";
    window.dispatchEvent(new CustomEvent("lecture-recording-state",{detail:window.LectureRecordingState()}));
  }
  async function startRecording(kind) {
    if (recording || starting || closing) return;
    if(draftOwner===null)return inform("Trwa sprawdzanie sesji konta. Spróbuj za chwilę.");
    if (!window.isSecureContext) return inform("Nagrywanie wymaga HTTPS albo localhost.", "error");
    if (!navigator.mediaDevices || !window.MediaRecorder) return inform("Ta przeglądarka nie obsługuje nagrywania. Użyj Chrome lub Edge na komputerze.", "error");
    if (kind !== "mic" && !navigator.mediaDevices.getDisplayMedia) return inform("Brak nagrywania dźwięku komputera w tej przeglądarce. Użyj Chrome lub Edge na komputerze.","error");
    const owner=draftOwner, attempt=++captureGeneration, withMic=kind==="screen"&&includeMic.checked;
    starting=true; setRecordingControls();
    status.textContent="Oczekiwanie na zgodę…";
    inform(kind==="mic"?"Zezwól na użycie mikrofonu.":kind==="youtube"
      ?"Wybierz „Ta karta” i włącz udostępnianie dźwięku karty. Następnie uruchom film YouTube w odtwarzaczu."
      :"Wybierz Cały ekran i włącz dźwięk systemowy lub wybierz kartę z włączonym udostępnianiem dźwięku.");
    try {
      // Call from the click handler, before awaiting storage: screen capture needs user activation.
      const capture=await (kind==="mic"
        ? navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true}})
        : navigator.mediaDevices.getDisplayMedia({video:true,audio:{echoCancellation:false,noiseSuppression:false,autoGainControl:false},systemAudio:kind==="youtube"?"exclude":"include",windowAudio:"system",selfBrowserSurface:kind==="youtube"?"include":"exclude",preferCurrentTab:kind==="youtube",surfaceSwitching:"exclude"}));
      if(attempt!==captureGeneration){capture.getTracks().forEach(t=>t.stop());return;}
      streams.push(capture);
      if(!capture.getAudioTracks().length)throw new Error("Nie udostępniono dźwięku. Wybierz kartę z audio albo cały ekran i zaznacz dźwięk systemowy. Dostępność zależy od systemu i przeglądarki.");
      let audioOnly=new MediaStream(capture.getAudioTracks());
      if(withMic){
        const environment=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true}});
        if(attempt!==captureGeneration){environment.getTracks().forEach(t=>t.stop());return;}
        streams.push(environment);
        const Audio=window.AudioContext||window.webkitAudioContext;
        const context=mixing=new Audio();await context.resume();
        if(attempt!==captureGeneration){void context.close().catch(()=>{});return;}
        const destination=context.createMediaStreamDestination();
        for(const source of [capture,environment]){
          const gain=context.createGain();gain.gain.value=0.8;
          context.createMediaStreamSource(new MediaStream(source.getAudioTracks())).connect(gain).connect(destination);
        }
        audioOnly=destination.stream;
      }
      await store.ready();
      if(attempt!==captureGeneration)return;
      session=new window.LectureRecording.RecordingSession({stream:audioOnly,owner,title:title.value.trim()||"Wykład",store,
        onState:part=>{began=part.createdAt;status.textContent=(kind==="mic"?"Nagrywanie mikrofonu":kind==="youtube"?"Nagrywanie YouTube":"Nagrywanie dźwięku komputera"+(withMic?" + mikrofon":""))+" · część "+part.part;stamp();},
        onError:error=>{inform("Nie udało się zapisać nagrania: "+(error?.message||"brak miejsca")+". Nagrywanie zatrzymano. Zapisane części pozostają na liście.","error");void finishRecording();},
        onPart:part=>{
          if(owner!==draftOwner)return;
          void renderRecordings();
          window.dispatchEvent(new CustomEvent("lecture-media-ready",{detail:{recordingId:part.id,owner,part:part.part,auto:true}}));
        }
      });
      const running=session;
      await running.start();
      if(attempt!==captureGeneration){await running.stop();return;}
      if(!running.active){releaseStreams();return;}
      recording=true;interval=setInterval(stamp,1000);
      recordBox.classList.add("active");
      // Do not abort a screen recording when a secondary audio track changes state.
      // The display video track is the stable signal that screen sharing was stopped.
      const stopTracks=kind==="screen"?capture.getVideoTracks():capture.getAudioTracks();
      stopTracks.forEach(track=>track.addEventListener("ended",()=>{if(attempt===captureGeneration)void finishRecording();},{once:true}));
      inform(kind==="youtube"
        ?"Przechwytuję dźwięk z wybranej karty. Uruchom odtwarzanie filmu. Zakończ nagrywanie po filmie; Whisper rozpocznie lokalną transkrypcję zapisanej części."
        :"Nagrywam. Co 2 godziny zapiszę osobną część i od razu rozpocznę kolejną. Transkrypcja ruszy po zapisie części.");
    } catch(error){
      if(attempt!==captureGeneration)return;
      releaseStreams();
      const denied=error?.name==="NotAllowedError";
      status.textContent=denied?"Odmowa dostępu":"Nagrywanie nie zostało uruchomione";
      inform(denied?"Nie udzielono zgody na nagrywanie. Sprawdź uprawnienia witryny.":String(error?.message||"Nie można rozpocząć nagrywania."),"error");
    } finally {
      if(attempt===captureGeneration){
        starting=false;setRecordingControls();
        if(!recording)releaseStreams();
      }
    }
  }
  async function finishRecording() {
    if(closing)return;
    if(!recording){
      if(starting){
        captureGeneration++;starting=false;
        const pending=session;session=null;void pending?.stop();
        releaseStreams();setRecordingControls();status.textContent="Rozpoczęcie nagrywania anulowane";
      }
      return;
    }
    recording=false;closing=true;starting=false;setRecordingControls();clearInterval(interval);interval=null;
    const ending=session;session=null;
    status.textContent="Zapisuję ostatnią część (maks. 02:00:00)…";
    try {await ending?.stop();}
    finally {
      releaseStreams();closing=false;setRecordingControls();
      recordBox.classList.remove("active");status.textContent="Nagrywanie zakończone";
      void renderRecordings();
    }
  }
  async function renderRecordings(){
    const owner=draftOwner,list=$("recordingsList");
    if(!store||!list||!owner)return;
    try {
      const records=await store.list(owner);if(owner!==draftOwner)return;
      list.replaceChildren();
      $("recordingsEmpty").hidden=records.length>0;
      for(const meta of records){
        const row=document.createElement("li");row.className="lecture-recording";
        const label=document.createElement("strong");label.textContent=meta.title+" · część "+meta.part;
        const info=document.createElement("small");info.textContent=new Date(meta.createdAt).toLocaleString("pl-PL")+" · "+(meta.status==="recording"?"zapis w toku / odzyskany fragment":window.LectureTranscriptCore.formatTime(meta.duration))+" · "+(meta.transcriptionStatus||"oczekuje na transkrypcję");
        const actions=document.createElement("div");actions.className="lecture-inline";
        const play=document.createElement("button");play.className="button";play.textContent="Odsłuchaj / pobierz";play.type="button";
        play.onclick=async()=>{try{const blob=await store.audio(meta);if(owner!==draftOwner)return;if(!blob.size)return inform("Ta część nie ma jeszcze zapisanych danych.","error");showMedia(blob,true,meta.id);$("downloadAudio").download="wyklad-czesc-"+meta.part+(meta.type.includes("mp4")?".mp4":".webm");}catch(e){inform("Nie można odczytać nagrania: "+e.message,"error");}};
        const retry=document.createElement("button");retry.className="button";retry.textContent="Transkrybuj część "+meta.part;retry.type="button";
        retry.disabled=meta.status==="recording"&&recording;
        retry.onclick=()=>{if(owner===draftOwner)window.dispatchEvent(new CustomEvent("lecture-media-ready",{detail:{recordingId:meta.id,owner,part:meta.part,auto:true}}));};
        const remove=document.createElement("button");remove.type="button";remove.className="button danger";remove.textContent="Usuń nagranie";remove.dataset.recordingRemove=meta.id;
        remove.disabled=recording||starting||closing;
        remove.onclick=async()=>{
          if(owner!==draftOwner||recording||starting||closing)return;
          if(!window.confirm("Usunąć „"+meta.title+"”, część "+meta.part+" i wszystkie jej fragmenty audio? Tekst transkrypcji pozostanie."))return;
          if(owner!==draftOwner)return;
          remove.disabled=true;
          window.dispatchEvent(new CustomEvent("lecture-recording-removing",{detail:{id:meta.id,owner}}));
          try{
            const deleted=await store.remove(meta.id,owner);if(owner!==draftOwner)return;
            if(!deleted)throw new Error("Nagranie nie jest już dostępne dla tego konta.");
            if(previewRecordingId===meta.id){
              $("audioPreview").pause();$("videoPreview").pause();
              $("audioPreview").removeAttribute("src");$("videoPreview").removeAttribute("src");
              $("mediaPlayer").hidden=true;mediaBlob=null;previewRecordingId=null;
              if(objectUrl){URL.revokeObjectURL(objectUrl);objectUrl=null;}
            }
            await renderRecordings();inform("Nagranie i jego fragmenty audio zostały usunięte. Tekst transkrypcji pozostaje.","success");
          }catch(error){if(owner===draftOwner){remove.disabled=false;inform("Nie udało się usunąć nagrania: "+error.message,"error");}}
        };
        actions.append(play,retry,remove);row.append(label,info,actions);list.append(row);
      }
    }catch(e){if(owner===draftOwner)inform("Zapis nagrań jest niedostępny: "+e.message,"error");}
  }
  window.addEventListener("lecture-transcription-state",()=>void renderRecordings());
  mic.addEventListener("click", () => startRecording("mic"));
  screen.addEventListener("click", () => startRecording("screen"));
  window.addEventListener("lecture-youtube-record",event=>{
    return inform("Przechwytywanie z YouTube jest tymczasowo nieaktywne.", "error");
    const parsed=window.LectureYouTubeLinks?.parse(event.detail?.url);
    if(!parsed||parsed.id!==event.detail?.id)return inform("Nieprawidłowy adres YouTube.","error");
    void startRecording("youtube");
  });
  stop.addEventListener("click", finishRecording);
  window.addEventListener("beforeunload", event => {
    if (!recording && !starting && !closing) return;
    event.preventDefault(); event.returnValue = "";
  });
  function showMedia(blob, fromRecording = false, recordingId = null) {
    previewRecordingId=recordingId;
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = URL.createObjectURL(blob);
    $("mediaPlayer").hidden = false;
    const video = blob.type.startsWith("video/");
    $("audioPreview").hidden = video; $("videoPreview").hidden = !video;
    $("audioPreview").pause(); $("videoPreview").pause();
    $("audioPreview").removeAttribute("src"); $("videoPreview").removeAttribute("src");
    $(video ? "videoPreview" : "audioPreview").src = objectUrl;
    const save = $("downloadAudio");
    save.hidden = !fromRecording;
    if (fromRecording) { save.href = objectUrl; save.download = safeName() + (blob.type.includes("mp4") ? ".mp4" : ".webm"); }
    importButton.disabled = fromRecording;
  }
  const dropZone=$("lectureDropZone");
  function useImportedFile(file){
    if(recording||starting||closing){
      inform("Zakończ nagrywanie przed zaimportowaniem pliku.","error");
      return;
    }
    if(!file){importButton.disabled=true;return;}
    const accepted=/^(audio|video)\//i.test(file.type||"")||/\.(?:m4a|mp3|wav|webm|mp4|mov|mkv|avi|ogg|flac|aac)$/i.test(file.name||"");
    if(!accepted){
      inform("To nie jest obsługiwany plik audio lub wideo.","error");
      return;
    }
    mediaBlob=file;
    importButton.disabled=false;
    showMedia(mediaBlob);
    $("fileHint").textContent=mediaBlob.name+" ("+(mediaBlob.size/1024/1024).toFixed(1)+" MB)";
    window.dispatchEvent(new CustomEvent("lecture-media-ready",{detail:{blob:mediaBlob,auto:false}}));
  }
  fileInput.addEventListener("change",()=>useImportedFile(fileInput.files?.[0]||null));
  if(dropZone){
    let dragDepth=0;
    dropZone.addEventListener("click",()=>{if(!fileInput.disabled)fileInput.click();});
    dropZone.addEventListener("keydown",event=>{
      if(event.key!=="Enter"&&event.key!==" ")return;
      event.preventDefault();
      if(!fileInput.disabled)fileInput.click();
    });
    dropZone.addEventListener("dragenter",event=>{
      event.preventDefault();dragDepth++;
      if(event.dataTransfer?.types?.includes("Files"))dropZone.classList.add("is-dragover");
    });
    dropZone.addEventListener("dragover",event=>{
      event.preventDefault();
      if(event.dataTransfer)event.dataTransfer.dropEffect=fileInput.disabled?"none":"copy";
    });
    dropZone.addEventListener("dragleave",event=>{
      event.preventDefault();dragDepth=Math.max(0,dragDepth-1);
      if(!dragDepth)dropZone.classList.remove("is-dragover");
    });
    dropZone.addEventListener("drop",event=>{
      event.preventDefault();dragDepth=0;dropZone.classList.remove("is-dragover");
      const file=[...(event.dataTransfer?.files||[])].find(item=>item instanceof File);
      if(!file)return;
      try{
        const transfer=new DataTransfer();
        transfer.items.add(file);
        fileInput.files=transfer.files;
      }catch{
        // Some browsers prohibit assigning FileList; the same file still enters transcription.
      }
      useImportedFile(file);
    });
  }
  setRecordingControls();
  // Płatne API oraz opracowanie notatek wyłączone: transkrypcja działa lokalnie.
  window.addEventListener("pagehide", () => {
    clearTimeout(autosaveTimer);
    save();
    captureGeneration++;
    if (recording || starting) void finishRecording();
    if (objectUrl) URL.revokeObjectURL(objectUrl);
  });
})();
