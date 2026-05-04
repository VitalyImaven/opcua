import matplotlib.pyplot as plt
import numpy as np

READ_MS = 0.82

# --- Data ---
events = ['1ms', '2ms', '5ms', '10ms', '20ms', '50ms', '100ms', '200ms']
event_vals = [1, 2, 5, 10, 20, 50, 100, 200]
max_vars = [round(e / READ_MS) for e in event_vals]

# Colors: gradient from red (few vars) to green (many vars)
colors = ['#ff2244', '#ff4455', '#ff6644', '#e94560', '#cc6633', '#44aa66', '#22bb77', '#00cc88']

fig, ax = plt.subplots(figsize=(14, 7))
fig.patch.set_facecolor('#1a1a2e')
ax.set_facecolor('#16213e')

bars = ax.bar(events, max_vars, color=colors, width=0.65, edgecolor='#2a3a5a', linewidth=1.2)

# Value labels on top of each bar
for bar, val in zip(bars, max_vars):
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 4,
            f'{val} vars', ha='center', va='bottom', fontsize=14,
            fontweight='bold', color='white')

# Horizontal lines for common scenarios
scenarios = [
    (200, '#ff4444', '200 vars (full set) — need ≥164ms events'),
    (50, '#ffaa00', '50 vars — need ≥41ms events'),
    (12, '#44ddff', '12 vars — need ≥10ms events'),
    (1, '#00ff88', '1 var — need ≥1ms events'),
]
for yval, clr, label in scenarios:
    ax.axhline(y=yval, color=clr, linestyle='--', alpha=0.6, linewidth=1.5)
    ax.text(7.6, yval + 3, label, fontsize=10, color=clr, fontweight='bold',
            ha='right', va='bottom',
            bbox=dict(facecolor='#1a1a2e', edgecolor=clr, alpha=0.85, pad=3, boxstyle='round,pad=0.3'))

ax.set_xlabel('Event Duration (how long the value changes)', fontsize=14, color='#e0e0e0', labelpad=12)
ax.set_ylabel('Max Variables You Can Monitor', fontsize=14, color='#e0e0e0', labelpad=12)
ax.set_title('OPC UA Detection Capability\n'
             'Read speed: 0.82 ms/variable  |  B&R PLC @ 192.168.101.10:4840',
             fontsize=16, color='#ffffff', fontweight='bold', pad=15)

ax.set_ylim(0, 270)
ax.tick_params(colors='#c0c0c0', labelsize=12)
ax.grid(axis='y', alpha=0.15, color='#4a4a6a')
for spine in ax.spines.values():
    spine.set_color('#2a3a5a')

plt.tight_layout()
plt.savefig('detection_capability.png', dpi=150, facecolor='#1a1a2e', edgecolor='none')
plt.show()
print("Saved: detection_capability.png")
