import {readFile,writeFile,readdir,mkdir} from 'node:fs/promises';
import {resolve,dirname,relative,isAbsolute} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';

// Generates protocol artifacts locally. Optional source checks read files only.
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const index=JSON.parse(await readFile(resolve(root,'catalog/endpoints.json'),'utf8'));
const pkg=JSON.parse(await readFile(resolve(root,'package.json'),'utf8'));
const write=process.argv.includes('--write'),checkouts=new Map(),ids=new Set(),operations=new Set();
const normalize=path=>path.split('?')[0].replace(/\$\{[^}]+\}/g,'{}').replace(/\{[^}]*\}/g,'{}');
const within=(base,path)=>{const rel=relative(base,path);return !isAbsolute(rel)&&rel!=='..'&&!rel.startsWith('../')&&!rel.startsWith('..\\');};
for(let i=2;i<process.argv.length;i++){
 if(process.argv[i]==='--write')continue;
 if(process.argv[i]!=='--source')throw new Error('Unknown argument: '+process.argv[i]);
 const value=process.argv[++i]||'',split=value.indexOf('='),name=value.slice(0,split);
 if(split<1||!index.sources[name])throw new Error('Expected --source refine=/path or --source yanhekit=/path');
 checkouts.set(name,resolve(value.slice(split+1)));
}
const evidence=e=>{const ref=index.sources[e.sourceProject];return {repository:ref.repository,revision:ref.revision,file:e.source,anchor:e.anchor,level:e.evidenceLevel};};
const sourceUrl=e=>{const ref=index.sources[e.sourceProject];return `${ref.repository}/blob/${ref.revision}/${e.source}`;};
for(const e of index.endpoints){
 if(ids.has(e.id))throw new Error('Duplicate endpoint ID: '+e.id);ids.add(e.id);
 if(!index.systems[e.system]||!index.sources[e.sourceProject]||!['GET','POST','PUT','HEAD'].includes(e.method)||!['read','write'].includes(e.effect))throw new Error('Invalid endpoint: '+e.id);
 if(!e.path.startsWith('/')||/[?#]/.test(e.path)||typeof e.anchor!=='string'||!e.anchor||!within(root,resolve(root,e.source)))throw new Error('Invalid path or source: '+e.id);
 const operation=e.system+':'+e.method+':'+normalize(e.path);if(operations.has(operation))throw new Error('Duplicate method/path: '+e.id);operations.add(operation);
 if(e.origin&&new URL(e.origin).protocol!=='https:')throw new Error('Non-HTTPS origin: '+e.id);
 const params=new Set();for(const p of e.parameters||[]){const key=p.in+':'+p.name;if(params.has(key))throw new Error('Duplicate parameter: '+e.id+' '+key);params.add(key);}
}

const sourcesChecked=[];
const prefix=/^\/(?:courseapi|coursesourceapi|vlabpassportapi|userapi|spidermaterial|v1|v2|api|internal-api|course|my|lib)(?:\/|$)/;
const call=/(?:\.(?:json|get|post|response|html)|new URL)\(\s*(['"`])([^'"`\r\n]+)\1/g;
for(const [project,checkout]of checkouts){
 const ref=index.sources[project],files=new Map();
 const git=spawnSync('git',['-C',checkout,'rev-parse','HEAD'],{encoding:'utf8',windowsHide:true,timeout:10000});
 const revision=git.status===0?git.stdout.trim():null;
 if(project==='refine'){
  for(const e of index.endpoints.filter(e=>e.sourceProject===project)){
   const path=resolve(checkout,e.source);if(!within(checkout,path))throw new Error('Source outside checkout');
   if(!files.has(e.source))files.set(e.source,await readFile(path,'utf8'));
   if(!files.get(e.source).includes(e.anchor))throw new Error('Source anchor changed: '+e.id+' in '+e.source);
  }
  for(const [file,text]of files)for(const match of text.matchAll(call)){
   const path=match[2];if(!prefix.test(path))continue;
   if(!index.endpoints.some(e=>e.sourceProject===project&&e.source===file&&normalize(e.path)===normalize(path)))throw new Error('Undocumented literal API call: '+file+' '+path);
  }
 }else if(project==='yanhekit'){
  const text=await readFile(resolve(checkout,ref.client),'utf8');files.set(ref.client,text);
  for(const e of index.endpoints.filter(e=>e.upstream)){
   if(!text.includes(e.path)||!text.includes('def '+e.upstream.split('.').at(-1)+'('))throw new Error('Upstream endpoint or method changed: '+e.id);
  }
 }
 sourcesChecked.push({project,expectedRevision:ref.revision,checkedRevision:revision,revisionMatches:revision===ref.revision,modules:files.size});
}

const cell=value=>String(value).replace(/\|/g,'\\|').replace(/[\r\n]+/g,' '),sections=[];
for(const [system,meta]of Object.entries(index.systems)){
 sections.push(`### ${meta.name}\n\n基础地址：\`${meta.origin}\`。会话：${meta.auth}。\n\n| 编号 | 请求 | 参数 / 请求体 | 消费的返回字段 | 来源 |\n| --- | --- | --- | --- | --- |`);
 for(const e of index.endpoints.filter(e=>e.system===system)){
  const up=index.sources.yanhekit,upstream=e.upstream?`；[yanhekit ${e.upstream}](${up.repository}/blob/${up.revision}/${up.client})`:'';
  sections.push(`| \`${e.id}\` | ${e.effect==='write'?'**写入** ':''}\`${e.method} ${e.origin||''}${e.path}\` | ${cell(e.request)} | ${cell(e.response)} | [源码](${sourceUrl(e)})${upstream} |`);
 }
 sections.push('');
}
const readmePath=resolve(root,'README.md'),current=await readFile(readmePath,'utf8');
const start='<!-- api-index:start -->',end='<!-- api-index:end -->';
if(current.split(start).length!==2||current.split(end).length!==2)throw new Error('README API markers must occur once');
const readme=current.slice(0,current.indexOf(start)+start.length)+'\n\n'+sections.join('\n').trim()+'\n\n'+current.slice(current.indexOf(end));
const ensureFile=async(path,expected)=>{if(write){await mkdir(dirname(path),{recursive:true});await writeFile(path,expected,'utf8');}else if(await readFile(path,'utf8')!==expected)throw new Error('Generated file is stale: '+relative(root,path)+'; run npm run docs:generate');};
await ensureFile(readmePath,readme);

for(const [system,meta]of Object.entries(index.systems)){
 const auth=['modern','legacy'].includes(system)?'bearerAuth':'sessionCookieHeader';
 const schemas=auth==='bearerAuth'?{bearerAuth:{type:'http',scheme:'bearer',description:meta.auth}}:{sessionCookieHeader:{type:'apiKey',in:'header',name:'Cookie',description:'已有合法登录会话的 Cookie 头。浏览器前端不能手动设置该头，需使用其现有会话与 credentials；这里不定义未知的 Cookie 名。'}};
 const document={openapi:'3.1.1',info:{title:index.title+' - '+meta.name,version:pkg.version,description:`社区观察规范。核对日期 ${index.checkedAt}；字段非完整官方 schema，例子为合成数据。认证、动态 URL 和未知边界见正文。`,license:{name:'MIT',identifier:'MIT'}},servers:[{url:meta.origin}],security:[{[auth]:[]}],paths:{},components:{securitySchemes:schemas},'x-checked-at':index.checkedAt,'x-sources':index.sources};
 for(const e of index.endpoints.filter(e=>e.system===system)){
  const parameters=[...e.path.matchAll(/\{([^}]+)\}/g)].map(m=>({name:m[1],in:'path',required:true,description:m[1]==='filePath'?'真实附件路径后缀，可能含多个路径段；直接使用平台返回的完整链接。':'所属系统返回的标识，避免跨平台或跨实体混用。',schema:{type:'string'}}));
  parameters.push(...structuredClone(e.parameters||[]));
  if(system==='lms'&&e.effect==='write'&&!e.origin)parameters.push({name:'X-XSRF-TOKEN',in:'header',required:false,description:'仅在当前会话存在 XSRF-TOKEN 时由其 URL 解码取得。',schema:{type:'string'}});
  const types=e.responseTypes||['application/json'],content={};
  for(const type of types){content[type]={schema:type==='application/octet-stream'?{type:'string',format:'binary'}:type==='text/html'?{type:'string'}:{}};if(type==='application/json'&&e.responseExample!==undefined)content[type].examples={synthetic:{summary:'合成结构示例，不是真实抓包',value:e.responseExample}};}
  const success={description:e.response,...(types.length?{content}:{})},responses={[e.successStatus||'200']:success,default:{description:'未完整枚举的 HTTP / 业务错误、登录页或资源不可用；按正文处理，不自动重试写请求。'}};
  for(const status of e.additionalSuccessStatuses||[])responses[status]={description:'参考客户端兼容的响应，仍需回读记录确认；不代表本次逐一实测。'};
  const operation={operationId:e.id.replace(/[.-]/g,'_'),summary:e.request,description:[e.response,e.note,e.schemaScope].filter(Boolean).join('\n\n'),tags:[system],parameters,responses,'x-effect':e.effect,'x-evidence':evidence(e),'x-response-fields':e.response};
  if(e.origin)operation.servers=[{url:e.origin}];if(e.security!==undefined)operation.security=e.security;
  if(e.requestBody)operation.requestBody=structuredClone(e.requestBody);
  if(e.upstream)operation['x-upstream-method']=e.upstream;
  (document.paths[e.path]||={})[e.method.toLowerCase()]=operation;
 }
 await ensureFile(resolve(root,'openapi',system+'.json'),JSON.stringify(document,null,2)+'\n');
}

async function markdownFiles(folder){const files=[];for(const entry of await readdir(folder,{withFileTypes:true})){if(['.git','node_modules','.cache','private'].includes(entry.name))continue;const path=resolve(folder,entry.name);if(entry.isDirectory())files.push(...await markdownFiles(path));else if(entry.name.endsWith('.md'))files.push(path);}return files;}
const markdown=await markdownFiles(root);let links=0;
for(const file of markdown)for(const match of (await readFile(file,'utf8')).matchAll(/\]\(([^\s)]+)(?:\s+"[^"]*")?\)/g)){
 const href=match[1];if(/^(?:https?:|mailto:|#)/.test(href))continue;
 const path=resolve(dirname(file),decodeURIComponent(href.split('#')[0]));
 if(!within(root,path))throw new Error('Link escapes reference directory: '+href);await readFile(path);links++;
}
console.log(JSON.stringify({ok:true,mode:'offline catalog, generated OpenAPI, source anchors and Markdown links',endpoints:index.endpoints.length,sharedWithYanhekit:index.endpoints.filter(e=>e.upstream).length,openapiDocuments:Object.keys(index.systems).length,markdownDocuments:markdown.length,localLinks:links,checkedAt:index.checkedAt,sourcesChecked}));
