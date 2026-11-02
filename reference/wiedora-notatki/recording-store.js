(() => {
  "use strict";
  let connection;
  function db(){
    if(!connection)connection=new Promise((resolve,reject)=>{
      const request=indexedDB.open("constant-lecture-audio-v1",1);
      request.onupgradeneeded=()=>{
        const database=request.result;
        database.createObjectStore("recordings",{keyPath:"id"}).createIndex("owner","owner");
        database.createObjectStore("chunks",{keyPath:["id","kind","index"]});
      };
      request.onsuccess=()=>resolve(request.result);
      request.onerror=()=>reject(request.error);
      request.onblocked=()=>reject(new Error("Zamknij starszą kartę programu i spróbuj ponownie."));
    });
    return connection;
  }
  async function transaction(names,mode,action){
    const database=await db();
    return new Promise((resolve,reject)=>{
      const tx=database.transaction(names,mode);let result;
      tx.oncomplete=()=>resolve(result);tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error||new Error("Zapis nagrania przerwany."));
      action(tx,value=>{result=value;});
    });
  }
  const range=(id,kind)=>IDBKeyRange.bound([id,kind,0],[id,kind,Number.MAX_SAFE_INTEGER]);
  const lockName=id=>"constant-lecture-recording:"+id;
  const busy=()=>new Error("Nagrywanie trwa w innej karcie. Najpierw je zatrzymaj.");
  function removeData(id,owner,canCheckActive){
    return transaction(["recordings","chunks"],"readwrite",(tx,done)=>{
      const recordings=tx.objectStore("recordings"),request=recordings.get(id);
      request.onsuccess=()=>{
        if(!request.result||request.result.owner!==owner){done(false);return;}
        if(request.result.status==="recording"&&!canCheckActive){done(new Error("Ta przeglądarka nie pozwala bezpiecznie usunąć niedokończonego nagrania. Użyj aktualnej przeglądarki Chrome lub Edge."));return;}
        recordings.delete(id);
        const chunks=tx.objectStore("chunks");
        chunks.delete(range(id,"audio"));chunks.delete(range(id,"clip"));
        done(true);
      };
    }).then(result=>{if(result instanceof Error)throw result;return result;});
  }
  const store={
    ready:db,
    // A live tab holds this lock until finalization. Closing/crashing the tab
    // releases it, so recovered fragments remain removable without a time lease.
    protect:async id=>{
      if(!navigator.locks)return ()=>{};
      return new Promise((resolve,reject)=>{
        const finished=navigator.locks.request(lockName(id),{ifAvailable:true},lock=>{
          if(!lock)throw busy();
          return new Promise(release=>resolve(()=>{release();return finished;}));
        });
        finished.catch(reject);
      });
    },
    create:meta=>transaction(["recordings"],"readwrite",tx=>tx.objectStore("recordings").put(meta)),
    append:(id,kind,index,blob)=>transaction(["recordings","chunks"],"readwrite",tx=>{
      const request=tx.objectStore("recordings").get(id);
      request.onsuccess=()=>{if(!request.result){tx.abort();return;}tx.objectStore("chunks").put({id,kind,index,blob});};
    }),
    complete:(id,update)=>transaction(["recordings"],"readwrite",tx=>{const s=tx.objectStore("recordings");const req=s.get(id);req.onsuccess=()=>{if(req.result)s.put({...req.result,...update});};}),
    list:owner=>transaction(["recordings"],"readonly",(tx,done)=>{const req=tx.objectStore("recordings").index("owner").getAll(owner);req.onsuccess=()=>done(req.result.sort((a,b)=>b.createdAt-a.createdAt));}),
    chunks:(id,kind)=>transaction(["chunks"],"readonly",(tx,done)=>{const req=tx.objectStore("chunks").getAll(range(id,kind));req.onsuccess=()=>done(req.result);}),
    remove:(id,owner)=>navigator.locks
      ? navigator.locks.request(lockName(id),{ifAvailable:true},lock=>{if(!lock)throw busy();return removeData(id,owner,true);})
      : removeData(id,owner,false),
    async audio(meta){return new Blob((await store.chunks(meta.id,"audio")).map(c=>c.blob),{type:meta.type});},
    async *clips(id){
      // Read one short file at a time; never decode two hours of PCM at once.
      let index=0;
      for(;;){
        const chunk=await transaction(["chunks"],"readonly",(tx,done)=>{const req=tx.objectStore("chunks").get([id,"clip",index]);req.onsuccess=()=>done(req.result);});
        if(!chunk)break;yield chunk.blob;index++;
      }
    }
  };
  window.LectureRecordingStore=store;
})();
