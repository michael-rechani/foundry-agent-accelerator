import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { foundryAgentUrl, validPortal } from '../src/foundry-links.ts'

const portal =
  'https://ai.azure.com/nextgen/r/qqqqqru7TMyN3e7u7u7u7g,rg-lab,,lab-account,lab-project'

describe('Foundry links', () => {
  it('accepts only the Foundry portal project prefix', () => {
    assert.equal(validPortal(portal), true)
    assert.equal(validPortal(null), true)
    for (const value of [
      '',
      'https://ai.azure.com',
      `${portal}/build`,
      portal.replace('https://', 'http://'),
      portal.replace('ai.azure.com', 'ai.azure.com.example.test'),
      'javascript:alert(1)',
      42,
    ])
      assert.equal(validPortal(value), false, String(value))
  })

  it('links an agent by its Foundry name', () => {
    assert.equal(
      foundryAgentUrl(portal, 'case-review-agent'),
      `${portal}/build/agents/case-review-agent/build`,
    )
    assert.equal(
      foundryAgentUrl(portal, 'a b/c'),
      `${portal}/build/agents/a%20b%2Fc/build`,
    )
    assert.equal(foundryAgentUrl(null, 'case-review-agent'), null)
    assert.equal(foundryAgentUrl(portal, ''), null)
  })
})
