# WCAG 2.2 · 2.3.1 闪烁阈值（原文摘录，2026-11-19 从 w3.org/TR/WCAG22 抓取）

> a flash or rapidly changing image sequence is below the threshold (i.e., content passes) if any of the following are true:
> - there are no more than three general flashes and / or no more than three red flashes within any one-second period; or
> - the combined area of flashes occurring concurrently occupies no more than a total of .006 steradians within any 10 degree visual field on the screen (25% of any 10 degree visual field on the screen) at typical viewing distance
>
> where:
> - A **general flash** is defined as a pair of opposing changes in relative luminance of 10% or more of the maximum relative luminance (1.0) where the relative luminance of the darker image is below 0.80; and where "a pair of opposing changes" is an increase followed by a decrease, or a decrease followed by an increase, and
> - A **red flash** is defined as any pair of opposing transitions involving a saturated red
>
> Exception: Flashing that is a fine, balanced, pattern such as white noise or an alternating checkerboard pattern with "squares" smaller than 0.1 degree (of visual field at typical viewing distance) on a side does not violate the thresholds.
>
> Note 1: For general software or web content, using a 341 x 256 pixel rectangle anywhere on the displayed screen area when the content is viewed at 1024 x 768 pixels will provide a good estimate of a 10 degree visual field for standard screen sizes and viewing distances (e.g., 15-17 inch screen at 22-26 inches).

用法：书和标准里涉及闪烁、频闪、高频硬切的条目，以这份原文为准。

换算口径（各书统一）：
- 341×256 px（在 1024×768 下）是规范给的**整个 10° 视野**的估计，不是闪烁面积上限；面积上限是 10° 视野的 **25%**（0.006 球面度）。
- 换算到其他屏幕时，按"观看距离 + 屏幕像素密度"算出 10° 视场在屏幕上的大小，用 0.006 球面度（圆形视场）求面积上限；不要把 10° 视野当正方形。
- 书里如果自己换算了像素值，必须写出所用的观看距离和像素密度，并和规范的 341×256@1024×768 参考值并列。本文件不给单一的像素数，因为结果取决于观看假设。
- 一次闪烁 = 一对相反的亮度变化；任意 1 秒内多于 3 次闪烁才不合格。较暗一侧的相对亮度须低于 0.80 才计入。红闪单独计数。
- 细密均衡的图案（白噪声、边长小于 0.1° 的棋盘格）不算违规；自动扫描要排除这类区域，否则会把颗粒和噪点误报成闪烁。
- 面积按"同时发生"的闪烁计。扫描若改用"同一秒内合计"，比规范严，须注明是偏严的近似。

## 补充原文（2026-11-20 从 w3.org/TR/WCAG22 术语表抓取，"general flash and red flash thresholds" 定义下的注释）

> **Note 2** A transition is the change in relative luminance (or relative luminance/color for red flashing) between adjacent peaks and valleys in a plot of relative luminance (or relative luminance/color for red flashing) measurement against time. A flash consists of two opposing transitions.
>
> **Note 3** The new working definition in the field for "pair of opposing transitions involving a saturated red" (from WCAG 2.2) is a pair of opposing transitions where, one transition is either to or from a state with a value R/(R + G + B) that is greater than or equal to 0.8, and the difference between states is more than 0.2 (unitless) in the CIE 1976 UCS chromaticity diagram. [ISO_9241-391]
>
> **Note 4** Tools are available that will carry out analysis from video screen capture. However, no tool is necessary to evaluate for this condition if flashing is less than or equal to 3 flashes in any one second.

说明：红闪的工作定义在 WCAG 2.2 正文术语表的注释里（不只在理解文档里）。R/(R+G+B) 按原文未说明是否线性化，书里若取线性化分量，须注明是自选取法。
