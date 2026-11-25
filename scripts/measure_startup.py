import time

t0 = time.perf_counter()
from apply_patch.gui.app import ApplyPatchApp
t1 = time.perf_counter()

app = ApplyPatchApp()
t2 = time.perf_counter()

# Schedule ready callback + auto-close after 2s
def on_ready():
    t3 = time.perf_counter()
    print(f"[STARTUP] Import:     {t1-t0:.3f}s")
    print(f"[STARTUP] App init:   {t2-t1:.3f}s")
    print(f"[STARTUP] Tk ready:   {t3-t2:.3f}s")
    print(f"[STARTUP] Total:      {t3-t0:.3f}s")
    app.after(100, app.destroy)  # Auto close

app.after(100, on_ready)
app.mainloop()