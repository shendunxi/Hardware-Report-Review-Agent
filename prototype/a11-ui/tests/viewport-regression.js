// Browser regression: run via the persistent browser's read-only evaluate API
// with the review page at scrollY=0, at 1440x900 and 1280x720.
// The narrow layout is intentionally a vertically scrolling single column.
function assertReviewFits() {
  const workbench = document.querySelector('.review-workbench').getBoundingClientRect();
  if (workbench.bottom > innerHeight || workbench.left < 0 ||
      workbench.right > document.documentElement.clientWidth) {
    throw new Error('Review viewport overflow: ' + JSON.stringify({
      bottom: workbench.bottom, right: workbench.right, innerHeight,
      clientWidth: document.documentElement.clientWidth
    }));
  }
  return { bottom: workbench.bottom, right: workbench.right, innerHeight };
}
