export async function runVisibleOperation({
  initialStatus,
  onStatus,
  run,
  failureStatus,
}) {
  let lastStatus = initialStatus;
  const report = (status) => {
    lastStatus = status;
    onStatus(status);
  };

  report(initialStatus);
  try {
    return { ok: true, value: await run(report) };
  } catch (error) {
    report(failureStatus(error, lastStatus));
    return { ok: false, error };
  }
}
