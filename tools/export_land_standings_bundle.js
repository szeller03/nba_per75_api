/* NBA PER-75 — paste this into DevTools Console while on landofbasketball.com */
(async()=>{
 const pages=[];
 for(let y=1952;y<=2026;y++){
  const s=`${y-1}-${String(y).slice(-2)}`;
  const u=`https://www.landofbasketball.com/yearbyyear/${y-1}_${y}_standings.htm`;
  console.log(`[${pages.length+1}/75] ${s}`);
  try{
   const r=await fetch(u,{credentials:'include'});
   if(!r.ok) throw new Error(`HTTP ${r.status}`);
   pages.push({season:s,url:u,html:await r.text()});
  }catch(e){pages.push({season:s,url:u,error:String(e)});console.warn(s,e)}
  await new Promise(r=>setTimeout(r,800));
 }
 const blob=new Blob([JSON.stringify({version:1,pages},null,2)],{type:'application/json'});
 const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='land_standings_bundle.json';document.body.appendChild(a);a.click();a.remove();
 console.log(`DONE — ${pages.filter(x=>x.html).length}/${pages.length} pages exported.`);
})();
