import { app } from "/scripts/app.js";

console.log("[Grok Nodes] Batch Sync Extension Loading...");

app.registerExtension({
    name: "Grok.SyncBatchCount",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name === "GrokSDXLPromptBatch") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                if (onNodeCreated) {
                    onNodeCreated.apply(this, arguments);
                }

                console.log("[Grok Nodes] GrokSDXLPromptBatch Created, hooking count widget...");

                const countWidget = this.widgets?.find(w => w.name === "count");
                if (countWidget) {
                    const originalCallback = countWidget.callback;
                    countWidget.callback = function (value) {
                        try {
                            if (originalCallback) {
                                originalCallback.apply(this, arguments);
                            }
                        } catch (e) { }

                        try {
                            const new_val = parseInt(value);
                            if (isNaN(new_val)) return;

                            console.log("[Grok Nodes] Count widget changed to:", new_val, "Searching for Batch input...");

                            const syncBatch = () => {
                                try {
                                    let batchInput = null;

                                    // 1. Specific known IDs (Fastest)
                                    const ids = ["batchCountInput", "batch_count", "batchCount", "batch-count"];
                                    for (const id of ids) {
                                        const el = document.getElementById(id);
                                        if (el) { batchInput = el; break; }
                                    }

                                    // 2. Search by text content of ANY element (Robust for V2)
                                    if (!batchInput) {
                                        const allPossible = Array.from(document.querySelectorAll('label, span, div, p, th, button, b'));
                                        const batchEl = allPossible.find(el => {
                                            const t = el.textContent.trim().toLowerCase();
                                            return t === 'batch count' || t === 'batch' || (t.includes('batch') && t.includes('count'));
                                        });

                                        if (batchEl) {
                                            console.log("[Grok Nodes] Found likely label element:", batchEl.textContent);
                                            // Search upward and then downward for a number input
                                            const container = batchEl.closest('div[style*="flex"]') || batchEl.closest('div') || batchEl.parentElement;
                                            batchInput = container.querySelector('input[type="number"]') ||
                                                batchEl.nextElementSibling?.querySelector('input[type="number"]') ||
                                                batchEl.querySelector('input[type="number"]');
                                        }
                                    }

                                    // 3. Fallback: Query Selectors for common patterns
                                    if (!batchInput) {
                                        batchInput = document.querySelector(".comfy-menu-batch-count input") ||
                                            document.querySelector("input[title*='Batch count']") ||
                                            document.querySelector("input[aria-label*='Batch count']") ||
                                            document.querySelector(".pi-input-number-input"); // V2 prime-vue
                                    }

                                    if (batchInput) {
                                        console.log("[Grok Nodes] Identified Batch Count Input:", batchInput);
                                        if (batchInput.value !== new_val.toString()) {
                                            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                                            setter.call(batchInput, new_val);

                                            // Dispatch all possible events to trigger various framework reactive states
                                            batchInput.dispatchEvent(new Event("input", { bubbles: true }));
                                            batchInput.dispatchEvent(new Event("change", { bubbles: true }));

                                            // Special handle for V2 (PrimeVue / React)
                                            batchInput.focus();
                                            batchInput.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, key: "Enter" }));
                                            batchInput.blur();

                                            console.log("[Grok Nodes] UI Synced successfully.");
                                        } else {
                                            console.log("[Grok Nodes] UI already matches.");
                                        }
                                    } else {
                                        console.warn("[Grok Nodes] Could not locate Batch Count input in the DOM.");
                                    }
                                } catch (e) {
                                    console.error("[Grok Nodes] Sync error:", e);
                                }
                            };

                            syncBatch();
                            // Retry a few times as the UI might re-render or be lazy
                            setTimeout(syncBatch, 200);
                            setTimeout(syncBatch, 800);
                            setTimeout(syncBatch, 2000);
                        } catch (e) {
                            console.error("[Grok Nodes] Error in widget callback:", e);
                        }
                    };
                }
            };
        }
    }
});
