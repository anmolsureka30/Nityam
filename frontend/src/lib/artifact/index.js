/* Import order matters: evaluate and kernel define the physics and the frame
 * shape; probes and render build on those; mount uses all four. */
import { NS } from "./ns.js";
import "./kernel.js";
import "./evaluate.js";
import "./probes.js";
import "./render.js";
import "./mount.js";

export default NS;
