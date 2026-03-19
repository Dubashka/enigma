# Session state keys — single source of truth
SHEETS = "sheets"           # dict[str, pd.DataFrame] — parsed file data
RAW_BYTES = "raw_bytes"     # bytes — original file bytes for re-download
STAGE = "stage"             # str — current step in the flow
FILE_NAME = "file_name"     # str — original uploaded file name

# Stage values
STAGE_UPLOADED = "uploaded"
STAGE_COLUMNS = "columns_selected"
STAGE_MASKED = "masked"

# Phase 2 keys
SELECTED_COLUMNS = "selected_columns"  # dict[sheet_name, dict[col_name, bool]]
MASK_CONFIG = "mask_config"            # dict[sheet_name, dict[col_name, "text"|"numeric"]]
MAPPING = "mapping"                    # dict: {"text": {norm_val: pseudonym}, "numeric": {col: multiplier}}
MASKED_SHEETS = "masked_sheets"        # dict[str, pd.DataFrame]
STATS = "stats"                        # dict: {"masked_values": int, "unique_entities": int}
