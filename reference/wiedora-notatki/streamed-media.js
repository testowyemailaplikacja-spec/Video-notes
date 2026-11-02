/* Decode large audio/video files through the browser's media pipeline, not arrayBuffer(). */
(function(root,factory){
  const api=factory();
  if(typeof module!=="undefined"&&module.exports)module.exports=api;
  if(root)root.LectureStreamedMedia=api;
})(typeof globalThis!=="undefined"?globalThis:this,()=>{
  "use strict";
  const RATE=16000,SEGMENT=28;
  function supportsStreaming(){return !!((globalThis.AudioContext||globalThis.webkitAudioContext)?.prototype?.createMediaElementSource);}
  function open(file,options={}){
    if(!file||!file.size)throw new Error("Wybierz niepusty film lub nagranie.");
    if(!supportsStreaming())throw new Error("Ta przeglądarka nie obsługuje strumieniowego odczytu multimediów.");
    const Audio=globalThis.AudioContext||globalThis.webkitAudioContext;
    const context=new Audio();
    // A media element with a blob URL seeks/decodes from disk without copying the
    // entire 3 GB file into JavaScript memory.
    const video=(file.type||"").startsWith("video/")||/\.(?:mp4|m4v|mov|webm|mkv|avi)$/i.test(file.name||"");
    const player=document.createElement(video?"video":"audio");
    player.preload="auto";player.volume=1;player.playsInline=true;
    player.setAttribute("aria-hidden","true");
    player.style.cssText="position:fixed;width:1px;height:1px;top:-9999px;pointer-events:none";
    const url=URL.createObjectURL(file);
    player.addEventListener("loadedmetadata",()=>{
      const at=Math.max(0,Number(options.startAt)||0);
      if(at&&Number.isFinite(player.duration)&&at<player.duration-0.5){
        try{player.currentTime=at;}catch{}
      }
    });
    player.src=url;document.body.appendChild(player);
    const source=context.createMediaElementSource(player);
    const processor=context.createScriptProcessor(4096,2,1);
    const silence=context.createGain();silence.gain.value=0;
    source.connect(processor);processor.connect(silence);silence.connect(context.destination);
    let pending=null,finished=false,closed=false,playing=false;
    let blocks=[],count=0,absoluteSample=0,nextOutput=0;
    const targetSamples=RATE*SEGMENT;
    const sizeHint=()=>Number.isFinite(player.duration)&&player.duration>0?player.duration:0;
    const errMsg="Nie można odtworzyć ścieżki audio tego pliku. Spróbuj MP4 (H.264/AAC), WebM lub MP3 w Chrome/Edge. MKV może wymagać konwersji.";
    const fail=error=>{
      if(closed)return;playing=false;player.pause();
      const p=pending;pending=null;
      if(p)p.reject(error instanceof Error?error:new Error(String(error)));
    };
    const take=()=>{
      const total=count,pcm=new Float32Array(total);let offset=0;
      for(const block of blocks){pcm.set(block,offset);offset+=block.length;}
      blocks=[];count=0;return pcm;
    };
    const deliver=(isFinal=false)=>{
      if(closed)return;
      player.pause();playing=false;
      const pcm=count?take():null;
      const p=pending;pending=null;
      if(isFinal)finished=true;
      if(p)p.resolve(pcm);
    };
    processor.onaudioprocess=event=>{
      if(closed||!playing||player.paused||finished)return;
      const input=event.inputBuffer;
      const channels=input.numberOfChannels;
      if(!channels)return;
      const left=input.getChannelData(0),right=channels>1?input.getChannelData(1):left;
      const rate=context.sampleRate,step=rate/RATE;
      const start=absoluteSample,end=start+left.length;
      const out=new Float32Array(Math.ceil(left.length/step)+2);let length=0;
      // Linear interpolation across decoded frames, down-mixed to mono at 16 kHz.
      while(nextOutput<end-1){
        const idx=Math.max(0,Math.floor(nextOutput-start)),frac=Math.max(0,nextOutput-start-idx);
        const a=(left[idx]+right[idx])*0.5,b=(left[idx+1]+right[idx+1])*0.5;
        out[length++]=Math.max(-1,Math.min(1,a+(b-a)*frac));
        nextOutput+=step;
      }
      absoluteSample=end;
      if(length){blocks.push(out.subarray(0,length));count+=length;}
      if(count>=targetSamples)deliver(false);
    };
    player.addEventListener("ended",()=>deliver(true));
    player.addEventListener("error",()=>fail(new Error(errMsg)));
    const state={get duration(){return sizeHint();},get position(){return player.currentTime||0;},get ended(){return finished;},
      next(){
        if(closed)return Promise.resolve(null);
        if(finished)return Promise.resolve(count?take():null);
        if(pending)throw new Error("Odczyt fragmentu już trwa.");
        return new Promise((resolve,reject)=>{
          pending={resolve,reject};
          playing=true;
          // Keep playback at 1x to preserve voice pitch; ASR pauses between segments.
          const resume=context.state==="running"?Promise.resolve():context.resume();
          resume.then(()=>player.play()).catch(error=>{
            fail(new Error(error?.name==="NotAllowedError"?
              "Przeglądarka zablokowała odtwarzanie. Kliknij Transkrybuj ponownie i zezwól na odtwarzanie dźwięku.":errMsg));
          });
        });
      },
      close(){
        if(closed)return;closed=true;playing=false;finished=true;
        const p=pending;pending=null;if(p)p.reject(new Error("Odczyt filmu został przerwany."));
        processor.onaudioprocess=null;player.pause();player.removeAttribute("src");player.load();player.remove();
        try{source.disconnect();processor.disconnect();silence.disconnect();}catch{}
        URL.revokeObjectURL(url);void context.close().catch(()=>{});
      }
    };
    return state;
  }
  return Object.freeze({open,supportsStreaming,RATE,SEGMENT});
});
