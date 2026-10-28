import test from 'node:test'
import assert from 'node:assert/strict'
import { ensureGrobid, hasPort } from './grobid.mjs'

const bindings = { '8070/tcp': [{ HostIp: '127.0.0.1', HostPort: '8070' }] }
const quiet = () => {}

test('only accepts the expected loopback port mapping', () => {
  assert.equal(hasPort(bindings, 8070), true)
  assert.equal(hasPort({}, 8070), false)
  assert.equal(hasPort(bindings, 8072), false)
  assert.equal(hasPort({ '8070/tcp': [{ HostIp: '0.0.0.0', HostPort: '8070' }] }, 8070), false)
})

test('a healthy parser is reused without Docker operations', async () => {
  await ensureGrobid('http://127.0.0.1:8070', { log: quiet, ready: async () => true,
    docker: () => assert.fail('Existing healthy service must not be changed') })
})

function existingContainer(calls, mapping = bindings) {
  return args => {
    calls.push(args)
    if (args[0] === 'info') return 'fixture-version'
    if (args[0] === 'start') return args[1]
    if (args.at(-1) === 'researchguard-grobid') return null
    if (args[2] === '{{.Config.Image}}') return 'grobid/grobid:0.9.1-crf'
    if (args[2] === '{{.State.Running}}') return 'false'
    return JSON.stringify(mapping)
  }
}

test('starts the existing mapped container and waits for readiness without duplicates', async () => {
  const calls = []
  let checks = 0
  await ensureGrobid('http://127.0.0.1:8070', { log: quiet,
    ready: async () => ++checks > 1, docker: existingContainer(calls) })
  assert.deepEqual(calls.filter(args => args[0] === 'start'), [['start', 'researchguard-eval-grobid-20261016']])
  assert.equal(calls.some(args => args[0] === 'run'), false)
  assert.equal(checks, 2)
})

test('a check never starts or creates a container', async () => {
  const calls = []
  await ensureGrobid('http://127.0.0.1:8070', { log: quiet, checkOnly: true,
    ready: async () => false, docker: existingContainer(calls) })
  assert.equal(calls.some(args => ['start', 'run'].includes(args[0])), false)
})

test('rejects the original missing-port failure before starting a wrong container', async () => {
  const calls = []
  await assert.rejects(ensureGrobid('http://127.0.0.1:8070', { log: quiet,
    ready: async () => false, docker: existingContainer(calls, {}) }), /does not publish/)
  assert.equal(calls.some(args => ['start', 'run'].includes(args[0])), false)
})

test('custom unreachable services are not replaced by local Docker containers', async () => {
  await assert.rejects(ensureGrobid('https://parser.example.org', { log: quiet,
    ready: async () => false, docker: () => assert.fail('No Docker for a custom service') }), /custom service/)
})

test('a new workspace creates one fixed container with a loopback mapping', async () => {
  const calls = []
  let checks = 0
  await ensureGrobid('http://127.0.0.1:8070', { log: quiet, ready: async () => ++checks > 1,
    docker: args => {
      calls.push(args)
      if (args[0] === 'inspect') return null
      return 'fixture-result'
    } })
  const runs = calls.filter(args => args[0] === 'run')
  assert.equal(runs.length, 1)
  assert.equal(runs[0][runs[0].indexOf('--name') + 1], 'researchguard-grobid')
  assert.equal(runs[0][runs[0].indexOf('-p') + 1], '127.0.0.1:8070:8070')
  assert.ok(runs[0].includes('--pull=never'))
})
