import { startGateway } from "./server.js";

startGateway().catch((e) => {
  console.error(e);
  process.exit(1);
});
