export async function onRequest(context) {
  const url = new URL(context.request.url);
  const targetHost = 'okba2new-migre.vercel.app';
  const targetUrl = 'https://' + targetHost + url.pathname + url.search;
  
  const headers = new Headers(context.request.headers);
  headers.set('Host', targetHost);
  if (headers.has('Origin')) {
    headers.set('Origin', 'https://' + targetHost);
  }

  const modifiedRequest = new Request(targetUrl, {
    method: context.request.method,
    headers: headers,
    body: context.request.body,
    redirect: 'follow',
  });

  return fetch(modifiedRequest);
}
