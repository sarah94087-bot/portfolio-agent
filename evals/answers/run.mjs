// Runs Promptfoo with what the Python side needs, on every OS:
//   node answers/run.mjs t1|t2 [promptfoo eval flags]
// - PYTHONUTF8=1: Python's default encoding on Windows is the system code page; UTF-8 mode
//   keeps every file and pipe of the Python side in UTF-8, for the Hebrew cases. Set here,
//   since Promptfoo starts Python for the test cases before the config's `env` applies.
// - PROMPTFOO_PYTHON: the backend's virtualenv when there is one (local), else `python` (CI).
// - No telemetry and no update check: the run talks only to the providers it tests.
import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const evals = path.resolve(here, '..')
const win = process.platform === 'win32'
const [tier = 't1', ...flags] = process.argv.slice(2)
if (!['t1', 't2'].includes(tier)) {
  console.error('usage: node answers/run.mjs t1|t2 [promptfoo eval flags]')
  process.exit(2)
}

const venv = path.resolve(evals, '..', 'backend', '.venv', win ? 'Scripts/python.exe' : 'bin/python')
const env = {
  ...process.env,
  PYTHONUTF8: '1',
  PROMPTFOO_DISABLE_TELEMETRY: '1',
  PROMPTFOO_DISABLE_UPDATE: '1',
  EVAL_TIER: tier,
}
env.PROMPTFOO_PYTHON ??= existsSync(venv) ? venv : 'python'

const bin = path.join(evals, 'node_modules', '.bin', win ? 'promptfoo.cmd' : 'promptfoo')
const args = ['eval', '-c', path.join(here, 'promptfooconfig.yaml'),
  '-o', path.join('results', `promptfoo-${tier}-latest.json`), ...flags]
const run = spawnSync(win ? `"${bin}"` : bin, args, { cwd: evals, env, stdio: 'inherit', shell: win })
process.exit(run.status ?? 1)
