declare module "*?worker" {
  class ViteWorker extends Worker {
    constructor();
  }
  export default ViteWorker;
}
