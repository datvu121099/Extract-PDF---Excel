import re
import io
import os
import tempfile
import pandas as pd
from datetime import datetime
import streamlit as st
from llama_index.core import SimpleDirectoryReader

st.set_page_config(page_title="Tự động hóa Hóa đơn ERP", page_icon="🚀", layout="wide")

# --- THANH BÊN: TẢI TẬP TIN ---
with st.sidebar:
    st.header("📁 Nguồn Dữ Liệu")
    mapping_file = st.sidebar.file_uploader("1. Tải lên File Mapping (Excel)", type=["xlsx"])
    pdf_file = st.sidebar.file_uploader("2. Tải lên File Hóa đơn (PDF)", type=["pdf"])
    st.divider()
    st.info("Quy tắc: Ngày tháng chỉ được lấy từ trang đầu tiên của PDF.")

# --- TRUNG TÂM: CẤU HÌNH ---
st.title("🚀 Tự Động Hóa Đối Soát Hóa Đơn")
st.subheader("📝 Cấu Hình Thông Tin Chung (Header)")

c1, c2, c3 = st.columns(3)
with c1:
    vendor_id = st.text_input("Nhà cung cấp (*)", value="2000001667")
    order_type = st.text_input("Loại đơn hàng (*)", value="Dịch vụ")
    purchase_type = st.text_input("Loại mua hàng (*)", value="Chi phí dịch vụ")
    ma_po_val = st.text_input("Mã PO", value="PDV42500008881")
with c2:
    currency = st.text_input("Tiền tệ (*)", value="VND")
    exchange_rate = st.text_input("Tỷ giá (*)", value="1")
    order_date_input = st.text_input("Ngày đặt hàng (*)", value="31/01/2025")
    payment_policy = st.text_input("Chính sách thanh toán", value="Thanh toán ngay")
with c3:
    receive_date_input = st.text_input("Ngày nhận (*)", value="11/02/2025")
    process_limit = st.text_input("Hạn xử lý", value="14/02/2025")
    is_contract = st.selectbox("Hợp đồng khung?", ["FALSE", "TRUE"], index=0)
    is_invoice = st.selectbox("Có hóa đơn hay không?", ["TRUE", "FALSE"], index=0)

# --- CÁC HÀM XỬ LÝ ---
def get_store_lookup(file):
    if not file: return {}
    try:
        df = pd.read_excel(file)
        df.columns = [str(c).strip() for c in df.columns]
        df['Phone_Col'] = df['Cua_Hang'].astype(str).str.strip()
        df['Name_Col'] = df['So_TB'].astype(str).str.strip()
        df['CC_Col'] = df['Trung_tam_chi_phi'].astype(str).str.strip()
        
        def fix_p(v):
            v = v.split('.')[0]
            return "0" + v if len(v) == 9 else v
        
        df['PK'] = df['Phone_Col'].apply(fix_p)
        return {r['PK']: {"name": r['Name_Col'], "cc": r['CC_Col']} for _, r in df.iterrows()}
    except Exception as e:
        st.error(f"Lỗi đọc file Excel: {e}")
        return {}

def process_full_pdf(documents, lookup):
    # 1. Chỉ tìm ngày ở trang đầu tiên (Trang 0)
    first_page_content = documents[0].get_content()
    date_pattern = r"THÁNG:\s*(\d{2}/\d{2}/\d{4})"
    date_match = re.search(date_pattern, first_page_content)
    
    if date_match:
        try:
            dt = datetime.strptime(date_match.group(1), "%d/%m/%Y")
            global_month_str = dt.strftime("%m.%Y")
        except:
            global_month_str = "#N/A"
    else:
        global_month_str = "#N/A"

    # 2. Trích xuất dữ liệu dòng "Tổng" từ TẤT CẢ các trang
    extracted = []
    line_pattern = r"\|\s*([\w\d]+)\s*\|\s*Tổng\s*\|\s*([\d\.,]+)\s*\|"
    
    # Gom text toàn bộ các trang để xử lý dữ liệu dòng
    full_content = "\n".join([doc.get_content() for doc in documents])
    
    for line in full_content.split("\n"):
        m = re.search(line_pattern, line)
        if m:
            phone = m.group(1).strip()
            lookup_p = phone if phone.startswith("0") else "0" + phone
            info = lookup.get(lookup_p, {"name": "Không xác định", "cc": "N/A"})
            extracted.append({
                "raw_phone": phone,
                "store_name": info['name'],
                "cost_center": info['cc'],
                "total": m.group(2).strip(),
                "month": global_month_str # Luôn dùng ngày lấy được từ trang đầu
            })
    return extracted

# --- THỰC THI ---
if pdf_file and mapping_file:
    lookup = get_store_lookup(mapping_file)
    
    with st.spinner("Đang trích xuất dữ liệu từ PDF..."):
        try:
            with tempfile.TemporaryDirectory() as tmp:
                with open(os.path.join(tmp, pdf_file.name), "wb") as f:
                    f.write(pdf_file.read())
                documents = SimpleDirectoryReader(tmp).load_data()
            
            base_rows = process_full_pdf(documents, lookup)
            
            if base_rows:
                # --- FILE 1: MẪU ERP ---
                df_erp = pd.DataFrame([
                    {
                        "Chi tiết đơn hàng / Mã Sản phẩm (*)": "C7220904",
                        "Chi tiết đơn hàng / Mô tả": f"T {r['store_name']}/ {r['raw_phone']}/ Cước tháng {r['month']}",
                        "Chi tiết đơn hàng / Hàng tặng": "",
                        "hàng / Số lượng (*)": 1,
                        "hàng / Đơn vị mua (*)": "Pack",
                        "Chi tiết đơn hàng / Đơn giá (*)": r['total'],
                        "Chi tiết đơn hàng / Thuế(%)": "V10C",
                        "Chi tiết đơn hàng / Chiết khấu(%)": "",
                        "Chi tiết đơn hàng / Lệnh sản xuất": "",
                        "Chi tiết đơn hàng / Trung tâm chi phí": r['cost_center'],
                        "Chi tiết đơn hàng / Ngày nhận (*)": receive_date_input,
                        "Chi tiết đơn hàng / Phiếu yêu cầu": "",
                        "hàng / STT Dòng": i+1
                    } for i, r in enumerate(base_rows)
                ])

                headers = {
                    "Nhà cung cấp (*)": vendor_id, "Loại đơn hàng (*)": order_type,
                    "Loại mua hàng (*)": purchase_type, "Tiền tệ (*)": currency,
                    "Tỷ giá (*)": exchange_rate, "Ngày đặt hàng (*)": order_date_input,
                    "Chính sách thanh toán": payment_policy, "Ngày nhận (*)": receive_date_input,
                    "Hạn xử lý": process_limit, "Hợp đồng khung?": is_contract,
                    "Có hóa đơn hay không?": is_invoice, "Ghi chú": "Note"
                }
                for col, val in reversed(list(headers.items())):
                    df_erp.insert(0, col, "")
                    df_erp.at[0, col] = val

                # --- FILE 2: MẪU RÚT GỌN ---
                df_simple = pd.DataFrame([
                    {
                        "Diễn giải": f"{r['store_name']}/ {r['raw_phone']}/ Cuoc ĐT {r['month']}",
                        "Số lượng": 1,
                        "Đơn giá": 1,
                        "Thành tiền": r['total'],
                        "Mã PO": ma_po_val
                    } for r in base_rows
                ])

                st.divider()
                st.success(f"Xử lý hoàn tất! Tháng ghi nhận: {base_rows[0]['month']}")
                t1, t2 = st.tabs(["📄 Mẫu PO", "📑 Mẫu bảng kê ĐNTT"])
                
                with t1:
                    st.dataframe(df_erp, use_container_width=True)
                    b1 = io.BytesIO()
                    df_erp.to_excel(b1, index=False)
                    st.download_button("⬇️ Tải file Mẫu ERP", b1.getvalue(), "ERP_Template.xlsx")
                
                with t2:
                    st.dataframe(df_simple, use_container_width=True)
                    b2 = io.BytesIO()
                    df_simple.to_excel(b2, index=False)
                    st.download_button("⬇️ Tải file Tổng Hợp", b2.getvalue(), "Summary.xlsx")
            else:
                st.warning("Không tìm thấy dữ liệu.")
        except Exception as e:
            st.error(f"Lỗi: {e}")
else:
    st.info("Hãy tải lên đủ 2 file ở thanh bên để bắt đầu.")
