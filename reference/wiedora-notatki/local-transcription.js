(() => {
  "use strict";
  const core=window.LectureTranscriptCore,$=id=>document.getElementById(id);
  const startButton=$("transcribeFile"),cancelButton=$("cancelTranscription"),modelSelect=$("whisperModel");
  const transcript=$("transcript"),status=$("whisperStatus"),progress=$("whisperProgress"),counter=$("whisperCounter"),message=$("lectureMessage");
  const store=window.LectureRecordingStore,queue=[];
  let currentOwner=window.LectureNotesOwner?.()||"guest";
  let file=null,busy=false,activeWorker=null,awaiting=null,generation=0,activeJob=null,activeStream=null;
  window.LectureTranscriptionBusy=()=>busy;
  function inform(text,kind=""){message.className="lecture-message"+(kind?" "+kind:"");message.textContent=text;}
  function setStatus(text){status.textContent=text+(queue.length?" · w kolejce: "+queue.length:"");}
  function setProgress(done,total){progress.max=Math.max(1,total);progress.value=done;counter.textContent=done+" / "+total+" fragmentów";}
  function setBusy(value){busy=value;startButton.disabled=value||!file;cancelButton.disabled=!value;modelSelect.disabled=value;}
  function teardownWorker(reason="Przerwano transkrypcję."){
    generation++;
    if(awaiting){const wait=awaiting;awaiting=null;clearTimeout(wait.timer);wait.reject(new Error(reason));}
    activeWorker?.terminate();activeWorker=null;
    activeStream?.close();activeStream=null;
  }
  async function mark(job,update,token){
    if(token!==undefined&&token!==generation)return;
    if(!job?.recordingId||!store)return;
    await store.complete(job.recordingId,update);
    if(token!==undefined&&token!==generation)return;
    window.dispatchEvent(new CustomEvent("lecture-transcription-state"));
  }
  function cancel(){
    queue.length=0;if(!busy)return;
    void mark(activeJob,{transcriptionStatus:"przerwano — można wznowić"}).catch(()=>{});
    teardownWorker();setBusy(false);activeJob=null;
    setStatus("Przerwano. Rozpoznany tekst został zachowany.");
    inform("Transkrypcja zatrzymana. Nagrania pozostają zapisane; możesz wznowić z listy.");
  }
  cancelButton.addEventListener("click",cancel);
  window.addEventListener("lecture-recording-removing",event=>{
    const {id,owner}=event.detail||{};
    if(owner!==currentOwner)return;
    for(let i=queue.length-1;i>=0;i--)if(queue[i].recordingId===id)queue.splice(i,1);
    if(activeJob?.recordingId===id){
      teardownWorker("Nagranie jest usuwane.");activeJob=null;setBusy(false);
      setStatus("Usunięto część z kolejki transkrypcji.");void drain();
    }
  });
  window.addEventListener("lecture-account-change",event=>{
    currentOwner=event.detail?.owner||"guest";
    queue.length=0;teardownWorker();activeJob=null;file=null;setBusy(false);setProgress(0,1);setStatus("Wybierz nagranie do transkrypcji.");
  });
  window.addEventListener("lecture-media-ready",event=>{
    const detail=event.detail||{};
    if(detail.recordingId){
      if(detail.owner!==currentOwner)return;
      file=null;startButton.disabled=true;
      if(activeJob?.recordingId===detail.recordingId||queue.some(j=>j.recordingId===detail.recordingId))return;
      queue.push({...detail,model:modelSelect.value});void drain();return;
    }
    file=detail.blob||null;startButton.disabled=busy||!file;
    if(file&&detail.auto){queue.push({blob:file,model:modelSelect.value});void drain();}
    else if(file&&!busy)setStatus("Nagranie gotowe. Kliknij Transkrybuj lokalnie 1:1.");
  });
  function workerMessage(worker,type,data){
    return new Promise((resolve,reject)=>{
      if(worker!==activeWorker)return reject(new Error("Transkrypcja została przerwana."));
      const timer=setTimeout(()=>{
        if(awaiting?.timer!==timer)return;awaiting=null;
        reject(new Error(type==="ready"?"Model nie odpowiada. Sprawdź dostęp do Hugging Face/CDN i spróbuj modelu tiny.":"Przekroczono czas rozpoznawania fragmentu. Spróbuj modelu tiny."));
      },type==="ready"?300000:240000);
      awaiting={type,resolve,reject,timer};
      worker.postMessage(data,data.audio instanceof Float32Array?[data.audio.buffer]:[]);
    });
  }
  function openWorker(){
    const worker=new Worker("/apps/notatki/whisper-worker.js?v=20261018-capture-2",{type:"module"});activeWorker=worker;
    function settle(error,data){const wait=awaiting;awaiting=null;if(wait){clearTimeout(wait.timer);error?wait.reject(error):wait.resolve(data);}}
    worker.onmessage=({data})=>{
      if(worker!==activeWorker)return;
      if(data?.type==="status")setStatus(data.text);
      if(data?.type==="download"&&data.status==="progress"&&Number.isFinite(data.progress))setStatus("Pobieranie modelu: "+Math.floor(data.progress)+"% — "+(data.file||"").split("/").pop());
      if(data?.type==="error"){const error=new Error(data.message||"Błąd modelu Whisper.");error.retryCPU=!!data.retryCPU;settle(error);}
      else if(data?.type===awaiting?.type)settle(null,data);
    };
    worker.onerror=event=>{if(worker!==activeWorker)return;settle(new Error("Nie udało się uruchomić Whisper. Sprawdź dostęp do CDN i Hugging Face. "+(event.message||"")));event.preventDefault();};
    worker.onmessageerror=()=>{if(worker===activeWorker)settle(new Error("Nie można odczytać odpowiedzi modelu."));};
    return worker;
  }
  async function initializeWorker(model,token){
    if(token!==generation)throw new Error("Transkrypcja została przerwana.");
    let worker=openWorker();
    try{await workerMessage(worker,"ready",{type:"init",model});}
    catch(error){
      if(!error.retryCPU||token!==generation)throw error;
      worker.terminate();activeWorker=null;
      setStatus("WebGPU niedostępne. Uruchamiam nowy silnik na CPU…");
      worker=openWorker();await workerMessage(worker,"ready",{type:"init",model:"tiny",forceCPU:true});
    }
    return worker;
  }
  async function decodeAudio(blob){
    const Audio=window.AudioContext||window.webkitAudioContext;
    if(!Audio||!window.OfflineAudioContext)throw new Error("Użyj Chrome lub Edge na komputerze — brak dekodowania audio.");
    const decoder=new Audio();
    try{return await decoder.decodeAudioData(await blob.arrayBuffer());}
    catch{throw new Error("Nie można odczytać nagrania. Spróbuj WAV, MP3 lub WebM w Chrome/Edge.");}
    finally{await decoder.close().catch(()=>{});}
  }
  async function resample(buffer,segment){
    const offline=new OfflineAudioContext(1,Math.max(1,Math.ceil(segment.duration*core.SAMPLE_RATE)),core.SAMPLE_RATE);
    const source=offline.createBufferSource();source.buffer=buffer;source.connect(offline.destination);source.start(0,segment.start,segment.duration);
    return (await offline.startRendering()).getChannelData(0).slice();
  }
  async function* sourceFiles(job){
    if(job.recordingId){for await(const blob of store.clips(job.recordingId))yield blob;}
    else yield job.blob;
  }
  function appendRecordedClip(job,index,text){
    if(window.LectureAppendTranscriptOnce){
      if(window.LectureAppendTranscriptOnce(job.recordingId,index,text)!==true)throw new Error("Nie udało się zapisać szkicu transkrypcji. Zwolnij miejsce i wznów nagranie.");
      return;
    }
    const previous=transcript.value;
    transcript.value=core.appendVerbatim(previous,text);transcript.dispatchEvent(new Event("input",{bubbles:true}));
    if(window.LectureSaveDraftNow?.()===false){
      transcript.value=previous;transcript.dispatchEvent(new Event("input",{bubbles:true}));
      throw new Error("Nie udało się zapisać szkicu transkrypcji. Zwolnij miejsce i wznów nagranie.");
    }
  }
  async function drain(){
    if(busy||!queue.length)return;
    const job=queue.shift();
    if(job.owner&&job.owner!==currentOwner){void drain();return;}
    activeJob=job;setBusy(true);const token=++generation,owner=currentOwner;
    let done=0,total=1,worker,stream,checkpointKey=null;
    try {
      let meta;
      if(job.recordingId){
        meta=(await store.list(job.owner)).find(m=>m.id===job.recordingId);
        if(token!==generation)return;
        if(!meta)throw new Error("Nie znaleziono nagrania tego konta.");
        if(meta.transcriptionStatus==="gotowa"){setStatus("Ta część ma już gotową transkrypcję.");return;}
        done=meta.completedClips||0;total=meta.clipCount||1;
      }
      await mark(job,{transcriptionStatus:"w toku"},token);
      if(token!==generation)return;
      setStatus("Odczytuję nagranie…");setProgress(done,total);
      let clipIndex=0,recognizedClips=0;
      // Large files are played and downmixed in 28-second blocks. The video
      // itself is never loaded into JS memory or uploaded to the server.
      const imported=!!job.blob&&!job.recordingId;
      const video=imported&&(job.blob.type.startsWith("video/")||/\.(?:mp4|m4v|mov|webm|mkv|avi)$/i.test(job.blob.name||""));
      if(imported&&(video||job.blob.size>25*1024*1024)){
        if(!window.LectureStreamedMedia?.supportsStreaming())throw new Error("Przeglądarka nie obsługuje strumieniowego odczytu dużych filmów.");
        checkpointKey="constant-lecture-video-checkpoint-v1:"+currentOwner+":"+job.blob.size+":"+job.blob.lastModified+":"+String(job.blob.name||"").slice(0,180);
        let resumeSeconds=0;
        try{
          const saved=JSON.parse(localStorage.getItem(checkpointKey)||"null");
          if(saved&&saved.seconds>0&&transcript.value.trim()&&transcript.value.endsWith(String(saved.tail||"")))resumeSeconds=Number(saved.seconds);
        }catch{}
        setStatus(resumeSeconds?"Wznawiam film od "+core.formatTime(resumeSeconds)+"…":"Otwieram strumień audio z filmu bez wczytywania całości do RAM…");
        stream=window.LectureStreamedMedia.open(job.blob,{startAt:resumeSeconds});activeStream=stream;
        clipIndex=Math.floor(resumeSeconds/28);
        // Start playback while the click gesture is fresh; loading the Whisper
        // model can happen in parallel with the first 28-second audio block.
        let nextPCM=stream.next().then(value=>({value}),error=>({error}));
        worker=await initializeWorker(job.model,token);
        if(token!==generation)return;
        while(token===generation){
          const next=await nextPCM;
          if(token!==generation)return;
          if(next.error)throw next.error;
          const pcm=next.value;
          if(!pcm)break;
          const duration=stream.duration;
          total=Math.max(1,Number.isFinite(duration)&&duration>0?Math.ceil(duration/28):clipIndex+1);
          setStatus("Film: rozpoznaję mowę od "+core.formatTime(clipIndex*28)+" — bez przesyłania pliku");
          const result=await workerMessage(worker,"result",{type:"transcribe",audio:pcm,index:clipIndex});
          if(token!==generation)return;
          transcript.value=core.appendVerbatim(transcript.value,result.text);
          transcript.dispatchEvent(new Event("input",{bubbles:true}));
          clipIndex++;recognizedClips++;setProgress(clipIndex,Math.max(total,clipIndex));
          // A checkpoint is valid only if its matching transcript was saved.
          if(window.LectureSaveDraftNow?.()!==false){
            try{localStorage.setItem(checkpointKey,JSON.stringify({seconds:stream.position,tail:transcript.value.slice(-100)}));}catch{}
          }
          nextPCM=stream.next().then(value=>({value}),error=>({error}));
        }
        stream.close();if(activeStream===stream)activeStream=null;
      } else for await(const blob of sourceFiles(job)){
        if(token!==generation)return;
        if(clipIndex++<done)continue;
        const audio=await decodeAudio(blob);if(token!==generation)return;
        if(!Number.isFinite(audio.duration)||audio.duration<=0)throw new Error("Plik nie zawiera rozpoznawalnego dźwięku.");
        const segments=core.planSegments(audio.duration);
        if(!job.recordingId){total=segments.length;setProgress(0,total);}
        if(!worker){worker=await initializeWorker(job.model,token);}
        let clipText="";
        for(let i=0;i<segments.length;i++){
          if(token!==generation)return;
          setStatus((job.part?"Część "+job.part+" · ":"")+"rozpoznaję mowę: "+core.formatTime(segments[i].start));
          const pcm=await resample(audio,segments[i]);if(token!==generation)return;
          const result=await workerMessage(worker,"result",{type:"transcribe",audio:pcm,index:i});if(token!==generation)return;
          if(job.recordingId)clipText=core.appendVerbatim(clipText,result.text);
          else{transcript.value=core.appendVerbatim(transcript.value,result.text);transcript.dispatchEvent(new Event("input",{bubbles:true}));}
          if(!job.recordingId)setProgress(i+1,total);
        }
        recognizedClips++;
        if(job.recordingId){appendRecordedClip(job,clipIndex-1,clipText);done=clipIndex;await mark(job,{completedClips:done},token);if(token!==generation)return;setProgress(done,total);}
      }
      if(!recognizedClips&&!done)throw new Error("Brak kompletnych fragmentów do transkrypcji. Nagrywaj przez kilka sekund i spróbuj ponownie.");
      if(window.LectureSaveDraftNow?.()===false)throw new Error("Nie udało się zapisać szkicu transkrypcji. Zwolnij miejsce i spróbuj ponownie.");
      await mark(job,{transcriptionStatus:"gotowa"},token);
      if(token!==generation)return;
      window.dispatchEvent(new CustomEvent("lecture-document-completed",{detail:{owner,kind:"transcript"}}));
      if(checkpointKey){try{localStorage.removeItem(checkpointKey);}catch{}}
      setStatus("Ukończono transkrypcję 1:1.");inform("Transkrypcja gotowa. Sprawdź rozpoznane słowa z nagraniem.","success");
    }catch(error){
      if(token===generation){await mark(job,{transcriptionStatus:"błąd — można wznowić"},token).catch(()=>{});if(token!==generation)return;setStatus("Transkrypcja nie powiodła się.");inform(String(error?.message||error)+" Nagranie i rozpoznany tekst zostały zachowane.","error");}
    }finally{
      stream?.close();if(activeStream===stream)activeStream=null;
      if(token===generation){teardownWorker("Zakończono transkrypcję.");activeJob=null;setBusy(false);void drain();}
    }
  }
  startButton.addEventListener("click",()=>{if(!busy&&file){queue.push({blob:file,model:modelSelect.value});void drain();}});
  window.addEventListener("pagehide",()=>{queue.length=0;teardownWorker();});
  setBusy(false);setStatus("Wybierz plik albo nagraj wypowiedź.");
})();
