import { spawnSync } from 'node:child_process'

const image = 'grobid/grobid:0.9.1-crf'

function runDocker(args, { optional = false } = {}) {
  const result = spawnSync('docker', args, { encoding: 'utf8', windowsHide: true, timeout: 30000 })
  if (result.status === 0) return result.stdout.trim()
  if (optional) return null
  throw new Error('Docker could not complete "docker ' + args[0] + '". Check that Docker Desktop is running and try again.')
}

export function hasPort(bindings, port) {
  return (bindings?.['8070/tcp'] ?? []).some(binding => binding.HostPort === String(port)
    && ['127.0.0.1', '::1'].includes(binding.HostIp))
}

export async function parserReady(baseUrl) {
  try {
    const response = await fetch(baseUrl + '/api/isalive', { signal: AbortSignal.timeout(3000), redirect: 'error' })
    return response.ok && (await response.text()).trim() === 'true'
  } catch { return false }
}

export async function ensureGrobid(baseUrl, {
  checkOnly = false, log = console.log, docker = runDocker, ready = parserReady,
} = {}) {
  const url = new URL(baseUrl)
  if (url.username || url.password || url.search || url.hash || !['http:', 'https:'].includes(url.protocol)) {
    throw new Error('GROBID Base URL must be HTTP(S) without URL credentials, query or fragment.')
  }
  baseUrl = baseUrl.replace(/\/$/, '')
  if (await ready(baseUrl)) {
    log('[dev] GROBID ready: ' + baseUrl + ' (reusing the existing service)')
    return
  }
  if (url.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(url.hostname) || !['', '/'].includes(url.pathname)) {
    throw new Error('The configured GROBID endpoint is not ready. Automatic Docker startup supports a local HTTP endpoint only; start your custom service or use --no-grobid.')
  }
  docker(['info', '--format', '{{.ServerVersion}}'])
  const port = url.port || '80'
  const override = process.env.RESEARCHGUARD_GROBID_CONTAINER
  const names = override ? [override] : ['researchguard-grobid', 'researchguard-eval-grobid-20261016']
  let selected
  for (const name of names) {
    const inspected = docker(['inspect', '--format', '{{json .HostConfig.PortBindings}}', name], { optional: true })
    if (inspected === null) continue
    if (!hasPort(JSON.parse(inspected), port)) {
      throw new Error('GROBID container "' + name + '" does not publish loopback port ' + port + ' to container port 8070. Fix its mapping or select a correctly configured RESEARCHGUARD_GROBID_CONTAINER.')
    }
    const containerImage = docker(['inspect', '--format', '{{.Config.Image}}', name])
    if (containerImage !== image) throw new Error('The selected container does not use the required GROBID image: ' + image)
    selected = name
    break
  }
  if (override && !selected) throw new Error('The configured GROBID container was not found: ' + override)
  if (!selected && docker(['image', 'inspect', image, '--format', '{{.Id}}'], { optional: true }) === null) {
    throw new Error('Install the GROBID image once with: docker pull ' + image)
  }
  selected ??= 'researchguard-grobid'
  log('[dev] GROBID not ready; ' + (checkOnly ? 'normal startup will start ' : 'starting ') + selected)
  if (checkOnly) return
  const exists = docker(['inspect', '--format', '{{.State.Running}}', selected], { optional: true })
  if (exists === null) {
    docker(['run', '--detach', '--pull=never', '--init', '--ulimit', 'core=0', '--name', selected,
      '-p', '127.0.0.1:' + port + ':8070', image])
  } else if (exists === 'false') {
    docker(['start', selected])
  }
  const deadline = Date.now() + 120000
  let nextNotice = Date.now() + 10000
  while (Date.now() < deadline) {
    if (await ready(baseUrl)) {
      log('[dev] GROBID ready: ' + baseUrl)
      return
    }
    if (Date.now() >= nextNotice) {
      const running = docker(['inspect', '--format', '{{.State.Running}}', selected])
      if (running !== 'true') throw new Error('GROBID exited during startup. Inspect it with: docker logs --tail 50 ' + selected)
      log('[dev] Waiting for GROBID initialization…')
      nextNotice = Date.now() + 10000
    }
    await new Promise(resolve => setTimeout(resolve, 1000))
  }
  throw new Error('GROBID did not become ready within 120 seconds. Inspect it with: docker logs --tail 50 ' + selected)
}
