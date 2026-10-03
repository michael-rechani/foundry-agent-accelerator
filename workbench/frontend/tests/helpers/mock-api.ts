import type { Page, Request, Route } from '@playwright/test'

export type ApiCall = {
  route: Route
  request: Request
  path: string
  method: string
  respond: (json: unknown, status?: number) => Promise<void>
}

// Intercepts every /api/ request on the page so that tests only ever talk to
// local mocks. The handler decides how to answer each call; returning without
// answering leaves the request pending, which tests use to simulate a stall.
export function mockApi(page: Page, handler: (call: ApiCall) => unknown) {
  return page.route('**/api/**', async (route) => {
    const request = route.request()
    await handler({
      route,
      request,
      path: new URL(request.url()).pathname,
      method: request.method(),
      respond: (json, status = 200) => route.fulfill({ json, status }),
    })
  })
}
