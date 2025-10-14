FROM curlimages/curl:8.10.1

USER root
RUN apk add --no-cache bash jq dos2unix
WORKDIR /work
COPY . /work
RUN dos2unix /work/infra/elasticsearch/bootstrap.sh || true \
 && chmod +x /work/infra/elasticsearch/bootstrap.sh

USER curl_user
CMD ["/bin/bash", "/work/infra/elasticsearch/bootstrap.sh"]
