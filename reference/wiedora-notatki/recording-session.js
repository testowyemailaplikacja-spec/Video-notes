/* Independent audio containers: a two-hour archive and short, decodable ASR clips. */
(function(root,factory){
  const api=factory();
  if(typeof module!=="undefined"&&module.exports)module.exports=api;
  if(root)root.LectureRecording=api;
})(typeof globalThis!=="undefined"?globalThis:this,()=>{
  "use strict";
  const PART_MS=2*60*60*1000,CLIP_MS=28000;
  class RecordingSession {
    constructor(options){
      Object.assign(this,{partMs:PART_MS,clipMs:CLIP_MS,now:()=>Date.now(),setTimer:(callback,delay)=>globalThis.setTimeout(callback,delay),clearTimer:id=>globalThis.clearTimeout(id),onPart:()=>{},onError:()=>{},onState:()=>{}},options);
      this.MediaRecorder=options.MediaRecorder||globalThis.MediaRecorder;
      this.active=false;this.number=0;this.pending=new Set();this.failed=false;
      this.sessionId=globalThis.crypto?.randomUUID?.()||Date.now()+"-"+Math.random().toString(36).slice(2);
    }
    async start(){
      if(this.active)return;
      this.active=true;
      try{
        this.openPart();
        // Recording is ready only after its first durable metadata record.
        await this.current.writes;
        if(this.failed)throw new Error("Nie udało się uruchomić zapisu nagrania.");
      }catch(error){
        this.reportError(error);
        await this.stop();
        throw error;
      }
    }
    createRecorder(){
      const mime=["audio/webm;codecs=opus","audio/webm","audio/mp4"].find(t=>this.MediaRecorder.isTypeSupported(t));
      return new this.MediaRecorder(this.stream,{audioBitsPerSecond:64000,...(mime?{mimeType:mime}:{})});
    }
    reportError(error){
      if(this.failed)return;
      this.failed=true;this.onError(error);
      void this.stop();
    }
    persist(p,kind,index,blob){
      p.writes=p.writes.then(()=>this.store.append(p.id,kind,index,blob));
      p.writes.catch(e=>this.reportError(e));
    }
    openClip(p){
      const rec=this.createRecorder();
      let resolve;const finished=new Promise(r=>{resolve=r;});p.clips.push(finished);
      const chunks=[];
      rec.ondataavailable=e=>{if(e.data?.size)chunks.push(e.data);};
      rec.onerror=e=>this.reportError(e.error||new Error("Błąd nagrywania fragmentu."));
      // Preserve capture order, but do not leave a hole when an encoder emits
      // an empty container (for example just as the session is stopped).
      p.clipWrites=(p.clipWrites||Promise.resolve()).then(()=>finished).then(blob=>{if(blob?.size)this.persist(p,"clip",p.clipCount++,blob);});
      rec.onstop=()=>resolve(new Blob(chunks,{type:rec.mimeType}));
      p.clip=rec;
      try{rec.start(1000);}catch(error){resolve();throw error;}
      p.clipTimer=this.setTimer(()=>{
        if(!this.active||this.current!==p)return;
        const old=p.clip;
        try{this.openClip(p);if(old.state!=="inactive")old.stop();}
        catch(error){if(old.state!=="inactive")old.stop();this.reportError(error);}
      },this.clipMs);
    }
    openPart(){
      const rec=this.createRecorder();
      const p={id:this.sessionId+"-"+(++this.number),owner:this.owner,title:this.title,part:this.number,createdAt:this.now(),type:rec.mimeType,clipCount:0,clips:[],audioCount:0,rec};
      p.writes=Promise.resolve().then(async()=>{
        p.release=await this.store.protect?.(p.id);
        await this.store.create({id:p.id,owner:p.owner,title:p.title,part:p.part,createdAt:p.createdAt,type:p.type,status:"recording",duration:0});
      });
      p.writes.catch(e=>this.reportError(e));
      p.done=new Promise(resolve=>{p.resolve=resolve;});
      this.pending.add(p.done);p.done.then(()=>this.pending.delete(p.done));
      rec.ondataavailable=e=>{if(e.data?.size)this.persist(p,"audio",p.audioCount++,e.data);};
      rec.onerror=e=>this.reportError(e.error||new Error("Błąd nagrywania dźwięku."));
      p.finalize=async()=>{
        if(p.finalizing)return;p.finalizing=true;
        try{
          await p.clipWrites;await p.writes;
          const meta={duration:(p.endedAt-p.createdAt)/1000,status:"saved",clipCount:p.clipCount};
          await this.store.complete(p.id,meta);
          if(!this.failed)this.onPart({id:p.id,owner:p.owner,title:p.title,part:p.part,...meta});
        }catch(e){this.reportError(e);}finally{try{await p.release?.();}catch(e){this.reportError(e);}p.resolve();}
      };
      rec.onstop=p.finalize;
      this.current=p;rec.start(1000);p.started=true;this.openClip(p);
      p.timer=this.setTimer(()=>{
        if(!this.active||this.current!==p)return;
        try{this.openPart();this.seal(p);}catch(e){this.reportError(e);this.seal(p);}
      },this.partMs);
      this.onState({part:p.part,createdAt:p.createdAt});
    }
    seal(p){
      if(p.sealed)return;p.sealed=true;p.endedAt=this.now();
      this.clearTimer(p.timer);this.clearTimer(p.clipTimer);
      if(p.clip&&p.clip.state!=="inactive")p.clip.stop();
      if(p.rec.state!=="inactive")p.rec.stop();
      else if(!p.started)void p.finalize();
    }
    async stop(){
      this.active=false;
      if(this.current)this.seal(this.current);
      await Promise.all([...this.pending]);
    }
  }
  return {RecordingSession,PART_MS,CLIP_MS};
});
