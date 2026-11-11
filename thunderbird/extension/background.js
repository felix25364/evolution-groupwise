/* SPDX-License-Identifier: LGPL-2.1-or-later */
const connections = new Map();
function transport(key) {
  if (!connections.has(key)) connections.set(key, new GroupwiseTransport(browser.runtime));
  return connections.get(key);
}
// A host owns one login session. Each account gets an independent native port.
browser.groupwise.onRequest.addListener(async request => {
  try {
    const result = await transport(request.serverKey).request(request.op, request);
    await browser.groupwise.answer(request.id, {ok:true, result});
  } catch (error) {
    await browser.groupwise.answer(request.id, {ok:false, error:{code:error.code || "HOST_UNAVAILABLE"}});
  }
});
browser.groupwise.bootstrap();
browser.runtime.onMessage.addListener(async message => {
  if (message.op !== "setup") return;
  const t = transport("setup");
  let created;
  try {
    const info = await t.request("login", message.settings);
    created = await browser.groupwise.createAccount({...message.settings, ...info});
    const previous = connections.get(created.serverKey);
    if (previous && previous !== t) previous.close();
    connections.set(created.serverKey, t); connections.delete("setup");
    await browser.groupwise.sync(created.serverKey);
    return {ok:true, ...created};
  } catch (error) {
    if (!created) { t.close(); connections.delete("setup"); }
    return {ok:false, accountCreated:!!created, error:error.code || error.message};
  }
});

// Never route a GroupWise identity through another account's default SMTP server.
browser.compose.onBeforeSend.addListener(async (tab, details) => {
  if (await browser.groupwise.isGroupwiseIdentity(details.identityId)) return {cancel:true};
  return {};
});
