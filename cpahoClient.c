#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "MQTTClient.h"
#include <pthread.h>
#include <signal.h>
#include <wiringPi.h>
#include <wiringSerial.h>
#include <errno.h>

struct clientInfo {
    char *address;
    char *clientid;
    char *topic;
    char *payload;
    int qos;
    unsigned long int timeout;
};

/* Global variables and mutex */
char data[100];                 // Recieved data from Arduino
int withData = 0;               // Does the array has data?
int out = 0;                    // Exit thread
pthread_mutex_t dataMutex;      // Set data mutex.
pthread_mutex_t withDataM;       // Acces data availability
pthread_mutex_t outMutex;       // Out mutex
int finishP = 0;
volatile MQTTClient_deliveryToken deliveredToken;

/* Handle keyboard interruption Ctrl+C */
void handles(int sig)
{
    printf("Finishing program.\n");
    finishP = 1;
}

void *readArduino(void *dataN)
{
    // Open connection to serial port
    int serialPort;
    int finish = 0;
    int n, i;

    printf("Connecting to arduino on port: /devv/ttyACM0.\n");
    if ((serialPort = serialOpen("/dev/ttyACM0", 9600)) < 0)
    {
        fprintf(stderr, "Unable to open serial device: %s.\n", strerror(errno));
        pthread_exit((void*)0);
    }

    if (wiringPiSetup() == -1)
    {
        fprintf(stderr, "Unable to start wiringPi: %s\n", strerror(errno));
        pthread_exit((void*)0);
    }

    while(!finish)
    {
        n = serialDataAvail(serialPort);
        if (n > 0)
        {
            // Lock mutex and copy data to array
            pthread_mutex_lock(&dataMutex);
            for (i = 0; i < n; i++)
                data[i] = serialGetchar(serialPort);
            data[n] = '\0';
            pthread_mutex_unlock(&dataMutex);
            pthread_mutex_lock(&withDataM);
            withData = 1;
            pthread_mutex_unlock(&withDataM);
        }
        // Check if thread should finish
        pthread_mutex_lock(&outMutex);
        if (out)
            finish = 1;
        pthread_mutex_unlock(&outMutex);
    }

    printf("Finishing arduino thread");
    pthread_exit((void*)0);
}

void createThread(pthread_t *thread)
{
    pthread_attr_t attr;
    int rc;

    // Create mutex
    pthread_mutex_init(&dataMutex, NULL);
    pthread_mutex_init(&outMutex, NULL);
    pthread_mutex_init(&withDataM, NULL);

    // Initialize attribute and set to joinable
    pthread_attr_init(&attr);
    pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_JOINABLE);

    // Create thread
    rc = pthread_create(thread, &attr, readArduino, NULL);
    if (rc)
    {
        printf("ERROR; return code from pthread_create() is %d\n", rc);
        exit(-1);
    }
}

void destroyThread(pthread_t *thread)
{
    void *status;
    int rc;

    // Destroy mutex
    pthread_mutex_destroy(&dataMutex);
    pthread_mutex_destroy(&outMutex);
    pthread_mutex_destroy(&withDataM);
    
    rc = pthread_join(*thread, &status);
    if (rc)
    {
        printf("ERROR; return code from pthread_join() is %d\n", rc);
        exit(-1);
    }
    printf("Completed thread join with status %ld\n", (long)status);
}

/* Asynchronous call */
void delivered(void *context, MQTTClient_deliveryToken dt)
{
    printf("Message with token value %d delivery confirmed.\n", dt);
    deliveredToken = dt;
}

void msgarrvd(void *context, char *topicName, int topicLen, MQTTClient_message *message)
{
    printf("Message arrived.\n");
}

void connlost(void *context, char *cause)
{
    printf("\nConnection lost.\n");
    printf("\tCause: %s.\n", cause);
}

/*
*   Create the client structure with necessary data.
*/
void createClient(MQTTClient *client, struct clientInfo *cf, char *capath, char *group)
{
    MQTTClient_connectOptions conn_opts = MQTTClient_connectOptions_initializer;
    MQTTClient_SSLOptions ssl_opts = MQTTClient_SSLOptions_initializer;
    int rc;

    /* Configure SSL client options */
    ssl_opts.enableServerCertAuth = 0;
    ssl_opts.enabledGroups = group; /* Key exchange */
    ssl_opts.CApath = capath;
    conn_opts.ssl = &ssl_opts;

    MQTTClient_create(client, cf->address, cf->clientid, MQTTCLIENT_PERSISTENCE_NONE, NULL);
    conn_opts.keepAliveInterval = 20;
    conn_opts.cleansession = 1;

    MQTTClient_setCallbacks(*client, NULL, connlost, msgarrvd, delivered);
    printf("Creating client.\n");
    if ((rc = MQTTClient_connect(*client, &conn_opts)) != MQTTCLIENT_SUCCESS)
    {
        printf("Failed to connect, return code %d\n", rc);
        exit(EXIT_FAILURE);
    }
}

void delivereMessage(MQTTClient *client, struct clientInfo *cf)
{
    MQTTClient_message pubmsg = MQTTClient_message_initializer;
    MQTTClient_deliveryToken token;
    int rc;

    pubmsg.payload = cf->payload;
    pubmsg.payloadlen = strlen(cf->payload);
    pubmsg.qos = cf->qos;
    pubmsg.retained = 0;
    MQTTClient_publishMessage(*client, cf->topic, &pubmsg, &token);
    rc = MQTTClient_waitForCompletion(*client, token, cf->timeout);
    printf("Message: %s sent.\n", (char *)pubmsg.payload);
    printf("\nMessage with delivery token %d delivered\n", token);
}

void run(MQTTClient *client, struct clientInfo *cf)
{
    int read = 0;
    printf("Publishing to topic %s, with client %s.\n", cf->topic, cf->clientid);
    while (!finishP)
    {
        // Is there data available
        pthread_mutex_lock(&withDataM);
        if (withData == 1)
            read = 1;
        else
            read = 0;
        pthread_mutex_unlock(&withDataM);
        if (read == 1)
        {
            // Send data to broker
            if (cf->payload)
                free((void*)cf->payload);
            pthread_mutex_lock(&dataMutex);
            cf->payload = strdup(data);
            pthread_mutex_unlock(&dataMutex);
            pthread_mutex_lock(&withDataM);
            withData = 0;
            pthread_mutex_unlock(&withDataM);
            delivereMessage(client, cf);
        }   
    }
    printf("Sending signal to finish thread.\n");
    pthread_mutex_lock(&outMutex);
    out = 1;
    pthread_mutex_unlock(&outMutex);
    printf("Finishing main program.");
}

int main(int argc, char **argv)
{
    //Set signal handler
    signal(SIGINT, handles);
    struct clientInfo cf;
    MQTTClient client;
    pthread_t thread;
    int rc;

    /* Configure client options */
    cf.address = "ssl://192.168.1.99:8883";
    cf.clientid = "Test";
    cf.topic = "test/topic";
    cf.payload = "Hello there! From paho C";
    cf.qos = 1;
    cf.timeout = 10000L;

    char *capath = "/home/pi/Documents/certs/pqcerts2/ca.crt";
    char *group = "lightsaber";
    createClient(&client, &cf, capath, group);
    createThread(&thread);
    
    destroyThread(&thread);
    MQTTClient_disconnect(client, 10000);
    MQTTClient_destroy(&client);

    pthread_exit(NULL);
}
