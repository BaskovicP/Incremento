export async function runPopupStartupTasks({ loadConnection, inspectPage }) {
  const [connection, page] = await Promise.allSettled([
    Promise.resolve().then(loadConnection),
    Promise.resolve().then(inspectPage),
  ]);
  return { connection, page };
}
