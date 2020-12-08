#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "MQTTClient.h"
#include <pthread.h>

struct clientInfo {
    char *address;
    char *clientid;
    char *topic;
    char *payload;
    int qos;
    unsigned long int timeout;
};

struct threadData {
    char data[100];
    int out;
    pthread_mutex_t dataMutex;
    pthread_mutex_t outMutex;
};

/*
*   Create the client structure with necessary data.
*/
void createClient(MQTTClient *client, struct clientInfo *cf, char *capath, char *group)
{
    client = (MQTTClient *)malloc(sizeof(MQTTClient));
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
    MQTTClient_publishMessage(client, cf->topic, &pubmsg, &token);
    rc = MQTTClient_waitForCompletion(client, token, cf->timeout);
    printf("Message: %s sent.\n", (char *)pubmsg.payload);
    printf("\nMessage with delivery token %d delivered\n", token);
}

int main(int argc, char **argv)
{
    struct clientInfo cf;
    MQTTClient client;
    int rc;

    /* Configure client options */
    cf.address = "ssl://192.168.1.99";
    cf.clientid = "Test";
    cf.topic = "test/topic";
    cf.payload = "Hello there! From paho C";
    cf.qos = 1;
    cf.timeout = 10000L;

    char *capath = "/home/jash/Documentos/Maestria/certs/pqcerts2/ca.crt";
    char *group = "lightsaber";
    createClient(&client, &cf, capath, group);

    printf("Waiting for up to %d seconds for publication of %s\non topic %s for client with ClientID: %s.\n", (int)(cf.timeout/1000), cf.payload, cf.topic, cf.clientid);
    delivereMessage(&client, &cf);
    
    MQTTClient_disconnect(client, 10000);
    MQTTClient_destroy(&client);
    return 0;
}
