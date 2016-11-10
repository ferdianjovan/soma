#ifndef MAINWINDOW_H
#define MAINWINDOW_H

#include <QtWidgets/QMainWindow>
#include <QThread>
#include <QFile>
#include <QDir>
#include <QDebug>
#include <QDialog>
#include <QTextBrowser>
#include <QStringListModel>
#include <QLineEdit>
#include <QRegExpValidator>
#include <QSlider>
#include <QDateTime>
#include <QDateEdit>
#include <QLabel>
#include "rosThread.h"
#include "querybuilder.h"

namespace Ui {
class MainWindow;
}

class MainWindow : public QMainWindow
{
    Q_OBJECT

public:
    explicit MainWindow(QWidget *parent = 0);
    RosThread rosthread;
    ~MainWindow();

    void setMongoDBHostName(std::string hostname);
    void setMongoDBPort(std::string port);

    QDateTime calculateDateTimeFromTimestamp(long timestamp);

signals:
    void sliderValue(int val);
public slots:
    void handleMapInfoReceived();

private slots:
    void on_timestepSlider_valueChanged(int value);

    void on_roiComboBox_currentIndexChanged(const QString &arg1);

    void  handleSOMAObjectTypes(std::vector<std::string> typenames);

    void  handleSOMAROINames(std::vector<SOMAROINameIDConfig> roinameidconfigs);

    void on_queryButton_clicked();

    void on_resetqueryButton_clicked();

    void on_exportjsonButton_clicked();

    void on_sliderCBox_clicked(bool checked);

    void on_upperDateCBox_clicked(bool checked);

    void on_lowerDateCBox_clicked(bool checked);

    void on_lineEditTimeStepIntervalMinutes_editingFinished();

    void on_lineEditTimeStepIntervalHours_editingFinished();


    void on_lineEditTimeStepIntervalDay_editingFinished();

    void on_sliderLastButton_clicked();

    void on_sliderFirstButton_clicked();

private:
    Ui::MainWindow *ui;

    QThread* thread;
    int maxtimestep;
    int mintimestep;
    std::vector<SOMAROINameIDConfig> roinameidconfigs;
    mongo::BSONObj mainBSONObj;
    QString lastqueryjson;
    int timestep;
    SOMATimeLimits timelimits;
    QString datetimeformat;
    void calculateSliderLimits(long lowertimestamp, long uppertimestamp);
    void calculateDateIntervalforTimestep(int step);
    void setupUI();
   // std::string mongodbhost;
   // std::string mongodbport;
};

#endif // MAINWINDOW_H
