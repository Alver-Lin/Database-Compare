import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.sql.Blob;
import java.sql.Clob;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.Statement;
import java.sql.Types;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Line-oriented JSON bridge for OceanBase JDBC (works on Java 8).
 *
 * stdin/stdout: one JSON object per line.
 */
public class ObJdbcBridge {
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private Connection connection;
    private ResultSet resultSet;
    private List<String> columns = new ArrayList<String>();

    public static void main(String[] args) throws Exception {
        Class.forName("com.oceanbase.jdbc.Driver");
        ObJdbcBridge bridge = new ObJdbcBridge();
        BufferedReader reader = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
        String line;
        while ((line = reader.readLine()) != null) {
            line = line.trim();
            if (line.isEmpty()) {
                continue;
            }
            Map<String, Object> req;
            try {
                req = MAPPER.readValue(line, new TypeReference<Map<String, Object>>() {});
            } catch (Exception e) {
                emitError("invalid json: " + e.getMessage());
                continue;
            }
            String op = String.valueOf(req.get("op"));
            try {
                if ("connect".equals(op)) {
                    bridge.connect(req);
                    emitOk();
                } else if ("query".equals(op)) {
                    bridge.query(req);
                    Map<String, Object> out = new LinkedHashMap<String, Object>();
                    out.put("ok", Boolean.TRUE);
                    out.put("columns", bridge.columns);
                    emit(out);
                } else if ("fetch".equals(op)) {
                    int size = req.get("size") == null ? 1000 : ((Number) req.get("size")).intValue();
                    List<List<Object>> rows = bridge.fetch(size);
                    Map<String, Object> out = new LinkedHashMap<String, Object>();
                    out.put("ok", Boolean.TRUE);
                    out.put("rows", rows);
                    out.put("done", Boolean.valueOf(rows.size() < size));
                    emit(out);
                } else if ("execute".equals(op)) {
                    bridge.execute(req);
                    emitOk();
                } else if ("close_result".equals(op)) {
                    bridge.closeResult();
                    emitOk();
                } else if ("close".equals(op)) {
                    bridge.closeAll();
                    emitOk();
                } else if ("quit".equals(op)) {
                    bridge.closeAll();
                    emitOk();
                    break;
                } else {
                    emitError("unknown op: " + op);
                }
            } catch (Exception e) {
                emitError(e.getMessage() == null ? e.getClass().getName() : e.getMessage());
            }
        }
    }

    private void connect(Map<String, Object> req) throws Exception {
        closeAll();
        String url = String.valueOf(req.get("url"));
        String user = String.valueOf(req.get("user"));
        String password = req.get("password") == null ? "" : String.valueOf(req.get("password"));
        connection = DriverManager.getConnection(url, user, password);
        try {
            connection.setAutoCommit(true);
        } catch (Exception ignored) {
            // ignore
        }
    }

    @SuppressWarnings("unchecked")
    private void query(Map<String, Object> req) throws Exception {
        ensureConnection();
        closeResult();
        String sql = String.valueOf(req.get("sql"));
        List<Object> params = req.get("params") == null
                ? new ArrayList<Object>()
                : (List<Object>) req.get("params");
        PreparedStatement ps = connection.prepareStatement(sql);
        bind(ps, params);
        resultSet = ps.executeQuery();
        ResultSetMetaData meta = resultSet.getMetaData();
        columns = new ArrayList<String>();
        for (int i = 1; i <= meta.getColumnCount(); i++) {
            String label = meta.getColumnLabel(i);
            if (label == null || label.isEmpty()) {
                label = meta.getColumnName(i);
            }
            columns.add(label);
        }
    }

    @SuppressWarnings("unchecked")
    private void execute(Map<String, Object> req) throws Exception {
        ensureConnection();
        closeResult();
        String sql = String.valueOf(req.get("sql"));
        List<Object> params = req.get("params") == null
                ? new ArrayList<Object>()
                : (List<Object>) req.get("params");
        PreparedStatement ps = connection.prepareStatement(sql);
        try {
            bind(ps, params);
            ps.execute();
        } finally {
            ps.close();
        }
    }

    private List<List<Object>> fetch(int size) throws Exception {
        List<List<Object>> rows = new ArrayList<List<Object>>();
        if (resultSet == null) {
            return rows;
        }
        int count = Math.max(1, size);
        while (rows.size() < count && resultSet.next()) {
            List<Object> row = new ArrayList<Object>();
            for (int i = 1; i <= columns.size(); i++) {
                row.add(convert(resultSet, i));
            }
            rows.add(row);
        }
        return rows;
    }

    private Object convert(ResultSet rs, int index) throws Exception {
        Object value = rs.getObject(index);
        if (value == null || rs.wasNull()) {
            return null;
        }
        if (value instanceof Clob) {
            Clob clob = (Clob) value;
            return clob.getSubString(1, (int) Math.min(clob.length(), Integer.MAX_VALUE));
        }
        if (value instanceof Blob) {
            Blob blob = (Blob) value;
            byte[] bytes = blob.getBytes(1, (int) Math.min(blob.length(), Integer.MAX_VALUE));
            StringBuilder sb = new StringBuilder();
            for (byte b : bytes) {
                sb.append(String.format("%02x", b));
            }
            return sb.toString();
        }
        if (value instanceof BigDecimal) {
            BigDecimal bd = (BigDecimal) value;
            try {
                return bd.longValueExact();
            } catch (ArithmeticException ex) {
                return bd.doubleValue();
            }
        }
        if (value instanceof java.sql.Date || value instanceof java.sql.Time || value instanceof java.sql.Timestamp) {
            return String.valueOf(value);
        }
        if (value instanceof byte[]) {
            byte[] bytes = (byte[]) value;
            StringBuilder sb = new StringBuilder();
            for (byte b : bytes) {
                sb.append(String.format("%02x", b));
            }
            return sb.toString();
        }
        return value;
    }

    private void bind(PreparedStatement ps, List<Object> params) throws Exception {
        for (int i = 0; i < params.size(); i++) {
            Object value = params.get(i);
            if (value == null) {
                ps.setNull(i + 1, Types.VARCHAR);
            } else {
                ps.setObject(i + 1, value);
            }
        }
    }

    private void ensureConnection() throws Exception {
        if (connection == null || connection.isClosed()) {
            throw new IllegalStateException("not connected");
        }
    }

    private void closeResult() {
        if (resultSet != null) {
            try {
                Statement st = resultSet.getStatement();
                resultSet.close();
                if (st != null) {
                    st.close();
                }
            } catch (Exception ignored) {
                // ignore
            }
            resultSet = null;
        }
        columns = new ArrayList<String>();
    }

    private void closeAll() {
        closeResult();
        if (connection != null) {
            try {
                connection.close();
            } catch (Exception ignored) {
                // ignore
            }
            connection = null;
        }
    }

    private static void emitOk() throws Exception {
        Map<String, Object> out = new LinkedHashMap<String, Object>();
        out.put("ok", Boolean.TRUE);
        emit(out);
    }

    private static void emitError(String message) throws Exception {
        Map<String, Object> out = new LinkedHashMap<String, Object>();
        out.put("ok", Boolean.FALSE);
        out.put("error", message);
        emit(out);
    }

    private static void emit(Map<String, Object> payload) throws Exception {
        byte[] bytes = MAPPER.writeValueAsString(payload).getBytes(StandardCharsets.UTF_8);
        System.out.write(bytes);
        System.out.write('\n');
        System.out.flush();
    }
}
