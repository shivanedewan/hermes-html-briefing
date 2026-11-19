import { params, message, spinner, failure } from "./common.js";
const $ = (id) => document.getElementById(id);
const p = params(); const img = $("img"); const main = $("main");
const toggle = () => { document.body.classList.toggle("actual"); $("toggle").textContent = document.body.classList.contains("actual") ? "Fit" : "Actual size"; };
$("toggle").onclick = toggle; img.onclick = toggle;
message(main, spinner("Loading image…"));
img.onload = () => { message(main, null); $("info").textContent = `Image · ${img.naturalWidth} × ${img.naturalHeight} px`; };
img.onerror = () => failure(main, new Error("The image could not be decoded"));
if (p.src) img.src = p.src; else failure(main, new Error("No file was given"));
