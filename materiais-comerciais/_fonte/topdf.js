const {chromium}=require('playwright');const path=require('path');
(async()=>{const [,, html,pdf,fmt]=process.argv;const b=await chromium.launch();const p=await b.newPage();
await p.goto('file://'+path.resolve(html));await p.waitForTimeout(800);
await p.pdf({path:pdf,preferCSSPageSize:true,printBackground:true});await b.close();})();
