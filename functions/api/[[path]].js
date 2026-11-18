export async function onRequest(context) {
  const url = new URL(context.request.url);
  const targetUrl = 'https://okba2new-migre.vercel.app' + url.pathname + url.search;
  
  const headers = new Headers(context.request.headers);
  headers.set('Host', 'okba2new-migre.vercel.app');

  const modifiedRequest = new Request(targetUrl, {
    method: context.request.method,
    headers: headers,
    body: context.request.body,
    redirect: 'follow',
  });

  return fetch(modifiedRequest);
}
