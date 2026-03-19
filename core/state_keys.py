# Session state keys — single source of truth
SHEETS = "sheets"           # dict[str, pd.DataFrame] — parsed file data
RAW_BYTES = "raw_bytes"     # bytes — original file bytes for re-download
STAGE = "stage"             # str — current step in the flow
FILE_NAME = "file_name"     # str — original uploaded file name

# Stage values
STAGE_UPLOADED = "uploaded"
STAGE_COLUMNS = "columns_selected"
STAGE_MASKED = "masked"
