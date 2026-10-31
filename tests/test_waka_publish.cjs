const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const workflow = fs.readFileSync(path.join(__dirname, '../.github/workflows/waka_readme.yml'), 'utf8');
const source = workflow.split('          script: |\n')[1].split('\n').map(line => line.slice(12)).join('\n');
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const execute = new AsyncFunction('process', 'github', 'context', 'core', source);
const marker = value => `<!--START_SECTION:waka-->\n${value}\n<!--END_SECTION:waka-->`;
const stamp = date => date.toISOString().replace(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}:\d{2}:\d{2}).*/, '$3/$2/$1 $4');
const fresh = marker(`💬 Programming Languages:\nPython $&\nLast Updated on ${stamp(new Date())} UTC`);
async function run({generated=fresh, current='before\n'+marker('old')+'\nafter', conflicts=0, denied=false, corrupt=false}={}) {
  let remote = current, writes = 0, revision = 1;
  const github = {rest:{repos:{
    async getContent() {return {data:{sha:String(revision),content:Buffer.from(remote).toString('base64')}};},
    async createOrUpdateFileContents(input) {
      writes++;
      assert.equal(input.sha,String(revision));
      if (denied) throw Object.assign(new Error('permission denied'),{status:403});
      if (conflicts-->0) {
        remote='concurrent dashboard update\n'+remote; revision++;
        throw Object.assign(new Error('SHA changed'),{status:409});
      }
      remote = corrupt ? 'write was lost' : Buffer.from(input.content,'base64').toString(); revision++;
    }
  }}};
  await execute({env:{WAKA_METRICS:'README stats current output:\n\n'+generated.replace(/^<!--START_SECTION:waka-->\n|\n<!--END_SECTION:waka-->$/g,'')}},github,
    {repo:{owner:'tingfeng347',repo:'tingfeng347'},payload:{repository:{default_branch:'main'}}},{info:()=>{}});
  return {remote,writes};
}
(async()=>{
  const normal=await run(); assert.equal(normal.remote,'before\n'+fresh+'\nafter');
  const raced=await run({conflicts:1}); assert.equal(raced.writes,2); assert.equal(raced.remote,'concurrent dashboard update\nbefore\n'+fresh+'\nafter');
  const unchanged=await run({current:'before\n'+fresh+'\nafter'}); assert.equal(unchanged.writes,0);
  await assert.rejects(run({conflicts:3}),/SHA changed/);
  await assert.rejects(run({denied:true}),/permission denied/);
  await assert.rejects(run({current:'no marker'}),/markers are missing/);
  await assert.rejects(run({generated:marker('Last Updated on 31/10/2026 00:00:00 UTC')}),/incomplete/);
  await assert.rejects(run({generated:fresh.replace(/Last Updated on .* UTC/,'Last Updated on 24/10/2026 20:34:04 UTC')}),/stale/);
  await assert.rejects(run({corrupt:true}),/does not contain/);
  console.log('PASS: publish, concurrent SHA retry, preserve unrelated content, literal replacement, idempotence, retry exhaustion, denied permissions, missing markers, incomplete/stale output, remote verification');
})().catch(error=>{console.error(error);process.exitCode=1});
