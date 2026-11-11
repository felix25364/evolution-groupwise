/* SPDX-License-Identifier: LGPL-2.1-or-later */
document.querySelector("form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.target, button = form.querySelector("button"), status = document.querySelector("#status");
  button.disabled = true; status.textContent = "Connecting…";
  try {
    const settings = {host:form.host.value.trim(), port:Number(form.port.value), username:form.username.value,
      password:form.password.value, tls:form.tls.checked};
    const result = await browser.runtime.sendMessage({op:"setup", settings});
    form.password.value = "";
    status.textContent = result.ok ? "GroupWise account created and synchronized." : (result.accountCreated ? "Account saved; refresh failed: " : "Setup failed: ") + result.error;
  } catch (_) { status.textContent = "Setup failed. Check that the native host is installed."; }
  finally { form.password.value = ""; button.disabled = false; }
});

async function showAccounts() {
  const list = document.querySelector("#accounts"); list.replaceChildren();
  for (const account of await browser.groupwise.listAccounts()) {
    const row=document.createElement("p"),label=document.createElement("span"),button=document.createElement("button");
    label.textContent=account.name + (account.error ? " — " + account.error : "");
    button.textContent="Refresh";
    button.addEventListener("click",async()=>{
      button.disabled=true;
      try { await browser.groupwise.sync(account.key); document.querySelector("#status").textContent="Refresh completed."; }
      catch (_) { document.querySelector("#status").textContent="Refresh failed. Check the native host, server and saved password."; }
      finally { button.disabled=false; await showAccounts(); }
    });
    row.append(label," ",button); list.append(row);
  }
}
showAccounts().catch(()=>{document.querySelector("#status").textContent="GroupWise API unavailable.";});
