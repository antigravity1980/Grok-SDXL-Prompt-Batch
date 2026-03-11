import { app } from "/scripts/app.js";

app.registerExtension({
    name: "Grok.ImageGallery",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "GrokBatchImageGallery") {
            console.log("Grok Image Gallery Extension Loading...");

            // Initialize history and state
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                if (onNodeCreated) {
                    onNodeCreated.apply(this, arguments);
                }
                this.grokHistory = [];
                this.grokZoomedIndex = null;

                this.addWidget("button", "Clear Gallery", null, () => {
                    this.grokHistory = [];
                    this.grokZoomedIndex = null;
                    this.setDirtyCanvas(true, true);
                });
            };

            // Intercept execution results using our custom key 'grok_images'
            const onExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (message) {
                if (onExecuted) {
                    onExecuted.apply(this, arguments);
                }

                // We listen for 'grok_images' instead of 'images' so ComfyUI core ignores it
                if (message?.grok_images) {
                    const limitWidget = this.widgets.find(w => w.name === "history_limit");
                    const limit = limitWidget ? limitWidget.value : 100;

                    for (const imgData of message.grok_images) {
                        const url = `/view?filename=${encodeURIComponent(imgData.filename)}&type=${imgData.type}&subfolder=${encodeURIComponent(imgData.subfolder)}&t=${Date.now()}`;

                        const img = new Image();
                        img.src = url;
                        this.grokHistory.unshift(img);
                    }

                    if (this.grokHistory.length > limit) {
                        this.grokHistory = this.grokHistory.slice(0, limit);
                    }

                    this.setDirtyCanvas(true, true);
                }
            };

            const onMouseDown = nodeType.prototype.onMouseDown;
            nodeType.prototype.onMouseDown = function (e, pos, canvas) {
                if (this.grokHistory && this.grokHistory.length > 0) {
                    const headerHeight = LiteGraph.NODE_TITLE_HEIGHT || 30;
                    const widgetHeight = this.getWidgetHeight();

                    // Check if click is BELOW the widgets
                    if (pos[1] > headerHeight + widgetHeight) {
                        if (this.grokZoomedIndex !== null) {
                            this.grokZoomedIndex = null;
                            this.setDirtyCanvas(true, true);
                            return true; // Stop propagation
                        } else {
                            const rect = this.getGridRect();
                            if (rect && pos[1] >= rect.y) {
                                const idx = this.getGridIndexAt(pos[0], pos[1], rect);
                                if (idx !== null) {
                                    this.grokZoomedIndex = idx;
                                    this.setDirtyCanvas(true, true);
                                    return true; // Stop propagation
                                }
                            }
                        }
                    }
                }

                if (onMouseDown) {
                    return onMouseDown.apply(this, arguments);
                }
                return false;
            };

            // Layout helpers
            nodeType.prototype.getWidgetHeight = function () {
                if (!this.widgets || this.widgets.length === 0) return 0;
                let h = 0;
                for (const w of this.widgets) {
                    h += (w.computeSize ? w.computeSize()[1] : 22) + 4;
                }
                return h;
            };

            nodeType.prototype.getGridRect = function () {
                const headerHeight = LiteGraph.NODE_TITLE_HEIGHT || 30;
                const widgetHeight = this.getWidgetHeight();
                const padding = 10;
                return {
                    x: padding,
                    y: headerHeight + widgetHeight + padding,
                    w: this.size[0] - padding * 2,
                    h: this.size[1] - headerHeight - widgetHeight - padding * 2
                };
            };

            nodeType.prototype.getGridIndexAt = function (x, y, rect) {
                const num = this.grokHistory.length;
                if (num === 0) return null;

                const cols = Math.ceil(Math.sqrt(num));
                const rows = Math.ceil(num / cols);
                const cellW = rect.w / cols;
                const cellH = rect.h / rows;

                const col = Math.floor((x - rect.x) / cellW);
                const row = Math.floor((y - rect.y) / cellH);

                if (col >= 0 && col < cols && row >= 0 && row < rows) {
                    const idx = row * cols + col;
                    return idx < num ? idx : null;
                }
                return null;
            };

            nodeType.prototype.onDrawForeground = function (ctx) {
                const headerHeight = LiteGraph.NODE_TITLE_HEIGHT || 30;
                const widgetHeight = this.getWidgetHeight();
                const bodyW = this.size[0];
                const bodyH = this.size[1] - headerHeight - widgetHeight;

                // 1. CLEAR BACKGROUND COMPLETELY (Black slate) below widgets
                ctx.fillStyle = "#121212";
                ctx.fillRect(0, headerHeight + widgetHeight, bodyW, bodyH);

                if (!this.grokHistory || this.grokHistory.length === 0) {
                    ctx.fillStyle = "#444";
                    ctx.font = "italic 16px Arial";
                    ctx.textAlign = "center";
                    ctx.fillText("Gallery Empty", bodyW / 2, headerHeight + widgetHeight + bodyH / 2);
                    return;
                }

                const rect = this.getGridRect();

                if (this.grokZoomedIndex !== null) {
                    // 2. ZOOMED VIEW
                    const img = this.grokHistory[this.grokZoomedIndex];
                    if (img && img.complete) {
                        this.drawImageFit(ctx, img, rect);

                        // Close button overlay
                        ctx.fillStyle = "rgba(0,0,0,0.8)";
                        ctx.fillRect(rect.x + rect.w - 80, rect.y + 10, 70, 30);
                        ctx.strokeStyle = "#fff";
                        ctx.lineWidth = 1;
                        ctx.strokeRect(rect.x + rect.w - 80, rect.y + 10, 70, 30);

                        ctx.fillStyle = "white";
                        ctx.font = "bold 13px Arial";
                        ctx.textAlign = "center";
                        ctx.fillText("✕ CLOSE", rect.x + rect.w - 45, rect.y + 30);
                        
                        // Dimensions overlay at bottom
                        const dimText = `${img.naturalWidth} x ${img.naturalHeight}`;
                        ctx.fillStyle = "rgba(0,0,0,0.6)";
                        ctx.fillRect(rect.x + rect.w / 2 - 50, rect.y + rect.h - 30, 100, 25);
                        ctx.fillStyle = "white";
                        ctx.font = "bold 14px Arial";
                        ctx.textAlign = "center";
                        ctx.fillText(dimText, rect.x + rect.w / 2, rect.y + rect.h - 13);
                    }
                } else {
                    // 3. GRID VIEW
                    const num = this.grokHistory.length;
                    const cols = Math.ceil(Math.sqrt(num));
                    const rows = Math.ceil(num / cols);
                    const cellW = rect.w / cols;
                    const cellH = rect.h / rows;

                    for (let i = 0; i < num; i++) {
                        const img = this.grokHistory[i];
                        if (!img || !img.complete) continue;

                        const col = i % cols;
                        const row = Math.floor(i / cols);
                        const x = rect.x + col * cellW + 2;
                        const y = rect.y + row * cellH + 2;
                        const w = cellW - 4;
                        const h = cellH - 4;

                        this.drawImageFit(ctx, img, { x, y, w, h });
                    }
                }
            };

            // Strict Fit & Center Image
            nodeType.prototype.drawImageFit = function (ctx, img, rect) {
                if (!img || !img.complete) return;

                const imgRatio = img.naturalWidth / img.naturalHeight;
                const rectRatio = rect.w / rect.h;

                let drawW, drawH, drawX, drawY;
                if (imgRatio > rectRatio) {
                    drawW = rect.w;
                    drawH = rect.w / imgRatio;
                    drawX = rect.x;
                    drawY = rect.y + (rect.h - drawH) / 2;
                } else {
                    drawH = rect.h;
                    drawW = rect.h * imgRatio;
                    drawX = rect.x + (rect.w - drawW) / 2;
                    drawY = rect.y;
                }

                ctx.drawImage(img, drawX, drawY, drawW, drawH);
            };
        }
    }
});
