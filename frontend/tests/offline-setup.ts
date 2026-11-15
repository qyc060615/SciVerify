import { Socket } from 'node:net'
import { afterEach, beforeEach, vi } from 'vitest'

// These are offline component/unit tests. An accidental provider request must fail.
let restoreNetworkGuards: () => void
beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('Network is forbidden in offline tests.'))))
  const xhr = vi.spyOn(XMLHttpRequest.prototype, 'open').mockImplementation(() => {
    throw new Error('Network is forbidden in offline tests.')
  })
  const socket = vi.spyOn(Socket.prototype, 'connect').mockImplementation(() => {
    throw new Error('Network is forbidden in offline tests.')
  })
  restoreNetworkGuards = () => { xhr.mockRestore(); socket.mockRestore() }
})
afterEach(() => { restoreNetworkGuards(); vi.unstubAllGlobals() })
