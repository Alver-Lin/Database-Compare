import java.sql.*;
public class ObTest {
  public static void main(String[] args) throws Exception {
    Class.forName("com.oceanbase.jdbc.Driver");
    String url = "jdbc:oceanbase://k8s.gjj.jxgjj:22881";
    String user = "HSGJJ@jxgjj_dev";
    String pass = "HsGjjTest123";
    System.out.println("connecting " + url + " as " + user);
    try (Connection c = DriverManager.getConnection(url, user, pass)) {
      System.out.println("connected ok meta=" + c.getMetaData().getDatabaseProductName() + " " + c.getMetaData().getDatabaseProductVersion());
      try (Statement s = c.createStatement()) {
        ResultSet rs = s.executeQuery("SELECT USER FROM DUAL");
        if (rs.next()) System.out.println("user=" + rs.getString(1));
        rs = s.executeQuery("SELECT SYS_CONTEXT('USERENV','CURRENT_SCHEMA') FROM DUAL");
        if (rs.next()) System.out.println("schema=" + rs.getString(1));
        rs = s.executeQuery("SELECT COUNT(*) FROM ALL_TABLES");
        if (rs.next()) System.out.println("all_tables=" + rs.getString(1));
      }
    }
  }
}
