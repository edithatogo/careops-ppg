// Test-only evaluator for generated, trusted native formatter expressions.
// Input record values stay data; they are never concatenated into executable text.
const fs=require('fs');
const cases=JSON.parse(fs.readFileSync(0,'utf8'));
function evaluate(text,env){
 if(typeof text!=='string')return text;
 if(/^\[\$\w+\]$/.test(text))return env[text.slice(2,-1)]??'';
 if(!text.startsWith('='))return text;
 const expression=text.slice(1).replace(/\[\$(\w+)\]/g,(_,k)=>'get('+JSON.stringify(k)+')').replace(/@now/g,'get("now")').replace(/\bif\(/g,'choose(');
 return Function('get','choose','Number','Date','floor','toString','split','length','return ('+expression+');')(
  k=>env[k]??'',(a,b,c)=>a?b:c,Number,x=>new Date(x),Math.floor,x=>String(x),(x,s)=>String(x).split(s),x=>Array.isArray(x)?x.length:x?1:0);
}
function render(n,env){
 if(n.forEach){const i=n.forEach.indexOf(' in '),key=n.forEach.slice(0,i),values=evaluate('='+n.forEach.slice(i+4),env);return values.map(x=>render({...n,forEach:null},{...env,[key]:x})).join('');}
 if(n.style?.display&&evaluate(n.style.display,env)==='none')return '';
 if(n.txtContent!==undefined)return String(evaluate(n.txtContent,env));
 return (n.children||[]).map(c=>render(c,env)).join('');
}
process.stdout.write(JSON.stringify(cases.map(c=>render(c.formatter.rowFormatter,{...c.row,now:new Date(c.now)}))));
