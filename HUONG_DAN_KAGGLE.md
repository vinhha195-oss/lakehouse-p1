# Hướng dẫn chạy ma trận thí nghiệm trên Kaggle

Ma trận đầy đủ (228 lần chạy) được chia thành 4 notebook, mỗi notebook ứng với một mức u (tỷ lệ cập nhật trễ).
Bốn notebook chạy song song được; mỗi notebook tự dừng trước 11 giờ.

| Notebook | u | Số lần chạy |
|---|---|---|
| `notebooks/sensorlst_u00.ipynb` | 0% | 57 |
| `notebooks/sensorlst_u01.ipynb` | 1% | 57 + 3 lần hiệu chuẩn |
| `notebooks/sensorlst_u05.ipynb` | 5% | 57 + 3 lần hiệu chuẩn |
| `notebooks/sensorlst_u20.ipynb` | 20% | 57 + 3 lần hiệu chuẩn |

## Các bước (làm 4 lần, mỗi notebook một lần)

1. Đăng nhập kaggle.com. Tài khoản phải **xác minh số điện thoại** thì mới bật được Internet cho notebook.
2. **Create → New Notebook → File → Import Notebook**, chọn một file `.ipynb` ở trên.
3. Mở khung **Settings** bên phải và đặt:
   - **Accelerator: None**: chỉ dùng CPU, máy có 4 lõi và 30 GB RAM. Đừng chọn GPU vì GPU không giúp gì cho Spark ở đây.
   - **Internet: On**: cần để cài Java, PySpark, tải các gói Delta/Iceberg/Hudi và tải dữ liệu TSM-Bench.
4. Bấm **Save Version → Save & Run All (Commit) → Save**. Notebook sẽ chạy nền trên máy chủ Kaggle, nên bạn có thể tắt
   trình duyệt và tắt máy mà không ảnh hưởng.
5. Khi phiên bản chạy xong (khoảng 4–10 giờ), mở **Output** của phiên bản đó và tải về file `results_uXX.zip`.

## Gửi lại kết quả

Giải nén cả 4 file zip vào thư mục `C:\Users\Admin\lakehouse-p1\results\`. Sau khi giải nén sẽ có
`results/runs_u00`, `runs_u01`, `runs_u05` và `runs_u20`. Báo lại để Claude chạy phân tích:

```
python -m sensorlst.analyze results/runs_u00 results/runs_u01 results/runs_u05 results/runs_u20 --out results/report
```

Lệnh này sinh ra `results/report/summary.csv` và các hình `fig_*.png` để điền vào bài báo (`paper/main.tex`).

## Nếu có sự cố

- **Notebook dừng giữa chừng:** các lần chạy đã xong vẫn được lưu. Chạy lại cùng notebook đó sẽ chạy lại cả shard,
  vì Kaggle không giữ output giữa các phiên bản. Nên giảm `REPS` hoặc `BUDGET_HOURS` ở ô tham số đầu tiên.
- **Lỗi `apt-get` hoặc `pip`:** kiểm tra lại Internet đã bật On chưa.
- Có lỗi ở lần chạy nào thì chi tiết nằm trong file `results/runs_uXX/failures.jsonl`.
